# Web Executor and browser automation with Playwright
# Controls Chrome browser and extracts DOM for the LLM to read

import time
from typing import Dict, Any
from playwright.sync_api import sync_playwright, Page, Browser, BrowserContext


class WebExecutor:
    # Executes web actions using Playwright
    def __init__(self, headless: bool = False, slow_mo: int = 500, use_existing_browser: bool = False):
        # Initialize browser
        self.headless = headless
        self.slow_mo = slow_mo
        self.use_existing_browser = use_existing_browser

        # Start Playwright
        self.playwright = sync_playwright().start()

        if use_existing_browser:
            # Connect to existing Chrome (it must be started with --remote-debugging-port=9222)
            try:
                self.browser: Browser = self.playwright.chromium.connect_over_cdp("http://localhost:9222")
                # Use existing context and page
                self.context: BrowserContext = self.browser.contexts[0]
                self.page: Page = self.context.pages[0] if self.context.pages else self.context.new_page()
            except Exception as e:
                raise RuntimeError(
                    "Could not connect to existing Chrome. "
                    "Make sure Chrome is running with: "
                    "/Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome --remote-debugging-port=9222"
                ) from e
        else:
            # Launch new Chrome
            self.browser: Browser = self.playwright.chromium.launch(
                headless=self.headless,
                slow_mo=self.slow_mo,
                channel="chrome"  
            )

            # Create browser context with viewport size
            self.context: BrowserContext = self.browser.new_context(
                viewport={"width": 1280, "height": 720},  # Window size
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
            )
            self.page: Page = self.context.new_page()

        # Initialize element cache for [N] selector lookup
        self.last_elements = []

    def navigate(self, url: str):
        # Navigate to a URL and wait for page to load
        # Use 'domcontentloaded' instead of 'networkidle' for apps with persistent connections
        self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        time.sleep(3.0)  # Wait for SPAs to fully render

    def execute_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        # Execute an action from the LLM with retry logic
        action_type = action.get('action')

        # Try action again
        for attempt in range(1):
            try:
                # Route to specific action handler
                if action_type == 'click':
                    self._click(action)
                elif action_type == 'type':
                    self._type(action)
                elif action_type == 'navigate':
                    self._navigate(action)
                elif action_type == 'wait':
                    self._wait(action)
                elif action_type == 'scroll':
                    self._scroll(action)
                else:
                    return {"success": False, "error": f"Unknown action: {action_type}"}

                # Success and return result with metadata
                return {
                    "success": True,
                    "url": self.page.url,
                    "is_search_box": action.get("_is_search_box", False)
                }

            except Exception as e:
                if attempt == 1:  # Last attempt
                    return {"success": False, "error": str(e)}
                time.sleep(1)  # Wait before retry

    def _click(self, action: Dict[str, Any]):
        # Click an element
        selector = action.get('selector')

        # If selector is [N] format, we need to convert it to actual selector
        if selector and selector.startswith('[') and selector.endswith(']'):
            try:
                index = int(selector[1:-1])  # Extract N from [N]
                # Get the actual selector from DOM extraction results
                # This is stored in self.last_elements
                if hasattr(self, 'last_elements') and index <= len(self.last_elements):
                    actual_selector = self.last_elements[index - 1]['selector']
                    selector = actual_selector
            except (ValueError, IndexError, KeyError):
                pass  # Use original selector if conversion fails

        # Wait for element to be visible
        self.page.wait_for_selector(selector, state="visible", timeout=10000)

        # Try normal click, fallback to force click
        try:
            self.page.click(selector, timeout=5000)
        except:
            self.page.click(selector, force=True, timeout=5000)

        time.sleep(1.5)  # Wait for SPAs to update

    def _type(self, action: Dict[str, Any]):
        # Type text into an input field
        selector = action.get('selector')
        text = action.get('text', '')

        # Convert [N] format to actual selector
        if selector and selector.startswith('[') and selector.endswith(']'):
            try:
                index = int(selector[1:-1])
                if hasattr(self, 'last_elements') and index <= len(self.last_elements):
                    selector = self.last_elements[index - 1]['selector']
            except (ValueError, IndexError, KeyError):
                pass

        # Wait for input field
        self.page.wait_for_selector(selector, state="visible", timeout=10000)

        # Check if this is a search box also for auto submit
        is_search_box = self.page.evaluate(f"""
            (selector) => {{
                const elem = document.querySelector(selector);
                if (!elem) return false;

                // Check if it's a search input
                const type = (elem.getAttribute('type') || '').toLowerCase();
                const role = (elem.getAttribute('role') || '').toLowerCase();
                const placeholder = (elem.getAttribute('placeholder') || '').toLowerCase();
                const name = (elem.getAttribute('name') || '').toLowerCase();
                const id = (elem.getAttribute('id') || '').toLowerCase();

                return type === 'search' ||
                       role === 'searchbox' ||
                       placeholder.includes('search') ||
                       name.includes('search') ||
                       id.includes('search');
            }}
        """, selector)

        # Store for later return
        action['_is_search_box'] = is_search_box

        # Clear field and type text
        self.page.fill(selector, text)

        # Auto press Enter for search boxes 
        if is_search_box or action.get('press_enter'):
            print(f"  ⏎  Auto-pressing Enter (search box detected)")
            self.page.press(selector, "Enter")
            time.sleep(1.5)  # Wait for search results to load
        else:
            time.sleep(0.5)

    def _navigate(self, action: Dict[str, Any]):
        # Navigate to a new URL
        url = action.get('url')
        self.page.goto(url, wait_until="networkidle", timeout=30000)
        time.sleep(0.8)

    def _wait(self, action: Dict[str, Any]):
        # Wait for element to appear or wait for duration
        if action.get('selector'):
            self.page.wait_for_selector(action['selector'], timeout=10000)
        else:
            time.sleep(1)

    def _scroll(self, action: Dict[str, Any]):
        # Scroll the page
        if action.get('selector'):
            # Scroll to specific element
            self.page.locator(action['selector']).scroll_into_view_if_needed()
        else:
            # Scroll down by pixels
            distance = action.get('distance', 500)
            self.page.mouse.wheel(0, distance)
        time.sleep(0.5)

    def get_screenshot(self) -> bytes:
        # Capture screenshot of current page
        return self.page.screenshot(full_page=False)

    def get_current_url(self) -> str:
        # Get current page URL
        return self.page.url

    def get_page_title(self) -> str:
        # Get current page title
        return self.page.title()

    def extract_dom_context(self, max_elements: int = 50) -> str:
        # Extract interactive elements with indices for LLM to reference
        try:
            # JavaScript extracts visible interactive elements
            elements = self.page.evaluate("""() => {
                const results = [];
                let index = 1;

                // Helper: Check if element is truly visible
                const isVisible = (elem) => {
                    if (!elem) return false;
                    const rect = elem.getBoundingClientRect();
                    const style = window.getComputedStyle(elem);
                    return rect.width > 0 && rect.height > 0 &&
                           elem.offsetParent !== null &&
                           style.display !== 'none' &&
                           style.visibility !== 'hidden' &&
                           style.opacity !== '0';
                };

                // Helper: Get best text (priority: aria-label > placeholder > title > text)
                const getBestText = (elem) => {
                    return elem.getAttribute('aria-label') ||
                           elem.getAttribute('placeholder') ||
                           elem.getAttribute('title') ||
                           elem.getAttribute('alt') ||
                           elem.textContent.trim();
                };

                // Helper: Get selector
                const getSelector = (elem) => {
                    if (elem.id) return `#${elem.id}`;
                    if (elem.getAttribute('data-testid')) return `[data-testid="${elem.getAttribute('data-testid')}"]`;
                    if (elem.name) return `[name="${elem.name}"]`;
                    if (elem.placeholder) return `[placeholder="${elem.placeholder}"]`;
                    // Fallback to text-based selector
                    const text = getBestText(elem).substring(0, 30);
                    return text ? `${elem.tagName.toLowerCase()}:has-text("${text}")` : null;
                };

                // Extract interactive elements
                // Start with likely interactive elements, then check ARIA roles on divs/spans
                const selector = 'button, a, input, textarea, select, [role="button"], [role="link"], [role="menuitem"], [role="textbox"], [role="combobox"], [role="search"], [onclick], [cursor="pointer"], div[role], span[role]';

                document.querySelectorAll(selector).forEach((elem) => {
                    try {
                        if (!isVisible(elem)) return;

                        const text = getBestText(elem);
                        if (!text || text.length < 1) return;  // Skip empty

                        const elemSelector = getSelector(elem);
                        if (!elemSelector) return;  // Skip if no selector

                        // Get role for type
                        const role = elem.getAttribute('role');
                        const type = elem.type || role || elem.tagName.toLowerCase();

                        results.push({
                            index: index++,
                            tag: elem.tagName.toLowerCase(),
                            text: text.substring(0, 80),
                            selector: elemSelector,
                            type: type
                        });
                    } catch (e) {
                        // Skip elements that cause errors
                    }
                });

                return results;
            }""")

            # Limit elements
            elements = elements[:max_elements]

            # Store for [N] selector lookup
            self.last_elements = elements

            # Format: [index]<tag>text
            context = f"URL: {self.get_current_url()}\n\n"
            context += f"Interactive elements ({len(elements)}):\n"

            for elem in elements:
                # Format: [1]<button aria-label="Filter">Filter</button> → selector
                context += f"[{elem['index']}]<{elem['tag']}>{elem['text']}</{elem['tag']}> → {elem['selector']}\n"

            return context

        except Exception as e:
            return f"Error extracting DOM: {str(e)}"

    def close(self):
        # Clean up browser resources
        if self.use_existing_browser:
            # Don't close user's browser just disconnect
            if self.playwright:
                self.playwright.stop()
        else:
            # We launched the browser therefore we can close it
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
