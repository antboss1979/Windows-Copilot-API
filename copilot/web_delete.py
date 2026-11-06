"""Delete a Copilot web conversation through the saved browser profile.

This sends the same request the Copilot page sends when you press 刪除:

    POST https://copilot.cloud.microsoft/chat?fromcode=cmcv2&es=Click
    {"action": "DeleteConversation", "conversationId": "<id>"}

The request is made from inside the signed-in page, so the profile's login cookies
go with it. Save this file as copilot/web_delete.py.

Requirements: pip install playwright && playwright install chromium
The profile folder can only be opened by one browser at a time, so callers should
serialize calls (api.py does this with its upstream lock).
"""

import json

from playwright.sync_api import sync_playwright

DEFAULT_PROFILE_DIR = "session/profile"
PAGE_URL = "https://copilot.cloud.microsoft/chat?fromcode=cmcv2&es=Click"

_SEND_DELETE = """
async (conversationId) => {
    const response = await fetch('/chat?fromcode=cmcv2&es=Click', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Accept': 'application/json', 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'DeleteConversation', conversationId }),
    });
    return {
        status: response.status,
        contentType: response.headers.get('content-type') || '',
        text: await response.text(),
    };
}
"""


class WebDeleteError(RuntimeError):
    """The Copilot web delete did not confirm the deletion."""


def delete_conversation_in_browser(conversation_id: str,
                                   profile_dir: str = DEFAULT_PROFILE_DIR) -> bool:
    """Delete one Copilot conversation. Returns True when Copilot confirms it.

    Raises WebDeleteError when the page answers with something other than the
    JSON result, which usually means the profile is not signed in.
    """
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(profile_dir, headless=True)
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(PAGE_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)  # let the signed-in page finish loading
            reply = page.evaluate(_SEND_DELETE, conversation_id)
        finally:
            context.close()

    if reply["status"] != 200 or "application/json" not in reply["contentType"]:
        raise WebDeleteError(f"Copilot answered status {reply['status']} "
                             f"({reply['contentType']}); the profile may not be signed in.")
    try:
        data = json.loads(reply["text"])
    except ValueError as exc:
        raise WebDeleteError("Copilot's delete reply was not JSON.") from exc
    deleted = (data.get("result") or {}).get("conversationIdsDeleted") or []
    return conversation_id in deleted
