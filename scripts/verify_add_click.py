from clinic_invoice_bot.api_ops import get_settings
from clinic_invoice_bot.browser import open_browser
from clinic_invoice_bot.workflow import _click_add_service, _service_line_count, login


def main() -> None:
    settings = get_settings(headed=False)
    with open_browser(settings) as (_pw, _browser, page):
        login(page, settings)
        page.goto(settings.patient_services_url, wait_until="domcontentloaded")
        page.select_option("select[name='clinic_id']", "82")
        page.wait_for_selector("select[name='s_id']", timeout=15000)
        opts = page.eval_on_selector_all(
            "select[name='s_id'] option",
            """els => els
              .filter(o => o.value && o.textContent.trim() !== '.')
              .slice(0, 1)
              .map(o => ({v: o.value, t: o.textContent.trim()}))""",
        )
        print("pick", opts[0])
        page.select_option("select[name='s_id']", opts[0]["v"])
        page.fill("#SearchBox12", opts[0]["t"])
        before = _service_line_count(page)
        print("before", before)
        _click_add_service(page)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1200)
        after = _service_line_count(page)
        body = page.inner_text("body")
        print("after", after)
        print("url", page.url)
        ok = after > before or opts[0]["t"] in body
        print("OK" if ok else "FAIL")


if __name__ == "__main__":
    main()