from attachment_handler import AttachmentHandler
from link_renderer import GITHUB_DOWNLOAD_ALLOWLIST, GithubLinks, Location, ObsidianLinks

BASE = "https://example.atlassian.net"


class FakeAttachment:
    def __init__(self, filename, size=1024, payload=b"x"):
        self.filename = filename
        self.size = size
        self.content = f"{BASE}/attachment/{filename}"
        self._payload = payload
        self.fetched = False

    def get(self):
        self.fetched = True
        return self._payload


class FakeFields:
    def __init__(self, attachments):
        self.attachment = attachments


class FakeIssue:
    def __init__(self, attachments):
        self.fields = FakeFields(attachments)


def handler(tmp_path, allowlist, links=None):
    return AttachmentHandler(None, str(tmp_path / "attachments"),
                             download_allowlist=allowlist, links=links)


def github_at():
    return GithubLinks(BASE, set()).at(Location.ticket("MGD-1"))


def test_allowlist_downloads_images_and_documents(tmp_path):
    atts = [FakeAttachment("flow.png"), FakeAttachment("spec.pdf"),
            FakeAttachment("data.xlsx"), FakeAttachment("rows.csv")]
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    h.download_attachments(FakeIssue(atts))
    assert all(a.fetched for a in atts)


def test_allowlist_skips_archives_without_fetching(tmp_path):
    """Assert the bytes are never requested, not merely omitted from output."""
    zip_att = FakeAttachment("SupportArchive.zip", size=11_744_051)
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    h.download_attachments(FakeIssue([zip_att]))
    assert zip_att.fetched is False
    assert h.skipped == [("SupportArchive.zip", zip_att.content, 11_744_051)]


def test_none_allowlist_downloads_everything(tmp_path):
    """Obsidian style: unchanged behavior."""
    zip_att = FakeAttachment("SupportArchive.zip")
    h = handler(tmp_path, None)
    h.download_attachments(FakeIssue([zip_att]))
    assert zip_att.fetched is True
    assert h.skipped == []


def test_all_skipped_leaves_no_empty_attachments_dir(tmp_path):
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    h.download_attachments(FakeIssue([FakeAttachment("SupportArchive.zip")]))
    assert not (tmp_path / "attachments").exists()


# --- Review Focus 3 and 4 ----------------------------------------------------

def test_uppercase_extensions_match_the_allowlist(tmp_path):
    att = FakeAttachment("SCREENSHOT.PNG")
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    h.download_attachments(FakeIssue([att]))
    assert att.fetched is True


def test_extensionless_files_are_skipped_not_crashed(tmp_path):
    """Real vault data: binary_windows-x86-64 and UUID-named blobs."""
    atts = [FakeAttachment("binary_windows-x86-64"),
            FakeAttachment("6457c0a4-01c0-4ace-aa09-c4ed86107eb2")]
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST)
    h.download_attachments(FakeIssue(atts))
    assert not any(a.fetched for a in atts)
    assert len(h.skipped) == 2


def test_skipped_files_render_as_sized_jira_links(tmp_path):
    att = FakeAttachment("SupportArchive.zip", size=11_744_051)
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST, links=github_at())
    images, others = h.download_attachments(FakeIssue([att]))
    md = h.get_attachment_list_markdown(images, others)
    assert f"[SupportArchive.zip]({BASE}/attachment/SupportArchive.zip) (11.2 MB)" in md


def test_github_listing_uses_relative_image_links(tmp_path):
    att = FakeAttachment("flow.png")
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST, links=github_at())
    images, others = h.download_attachments(FakeIssue([att]))
    md = h.get_attachment_list_markdown(images, others)
    assert "![flow.png](attachments/flow.png)" in md


def test_obsidian_listing_is_unchanged(tmp_path):
    att = FakeAttachment("flow.png")
    h = handler(tmp_path, None)
    images, others = h.download_attachments(FakeIssue([att]))
    md = h.get_attachment_list_markdown(images, others)
    assert md == "## Attachments\n\n### Images\n\n![[flow.png]]\n"


def test_explicit_obsidian_renderer_matches_the_default(tmp_path):
    att = FakeAttachment("flow.png")
    h = handler(tmp_path, None, links=ObsidianLinks(BASE, set()).at(Location.ticket("MGD-1")))
    images, others = h.download_attachments(FakeIssue([att]))
    assert "![[flow.png]]" in h.get_attachment_list_markdown(images, others)


def test_reference_to_a_skipped_file_becomes_a_jira_link(tmp_path):
    att = FakeAttachment("SupportArchive.zip", size=2048)
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST, links=github_at())
    h.download_attachments(FakeIssue([att]))
    out = h.replace_attachment_references("see [^SupportArchive.zip]")
    assert f"({BASE}/attachment/SupportArchive.zip)" in out
    assert "attachments/SupportArchive.zip" not in out


def test_a_ticket_with_only_skipped_attachments_still_lists_them(tmp_path):
    att = FakeAttachment("SupportArchive.zip", size=2048)
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST, links=github_at())
    images, others = h.download_attachments(FakeIssue([att]))
    assert images == [] and others == []
    md = h.get_attachment_list_markdown(images, others)
    assert "## Attachments" in md
    assert "SupportArchive.zip" in md


def test_filenames_with_parens_are_encoded_in_github_references(tmp_path):
    """Real vault data: SupportArchiveD2DFE639(1).zip — but as a .png here so
    it is downloaded rather than skipped."""
    att = FakeAttachment("Screenshot(1).png")
    h = handler(tmp_path, GITHUB_DOWNLOAD_ALLOWLIST, links=github_at())
    h.download_attachments(FakeIssue([att]))
    out = h.replace_attachment_references("![](Screenshot(1).png)")
    assert "attachments/Screenshot%281%29.png" in out
