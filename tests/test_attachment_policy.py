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


# --- Attachments that never reached disk -------------------------------------

class ExplodingAttachment(FakeAttachment):
    def get(self):
        raise RuntimeError("403 Forbidden")


def test_failed_download_renders_as_a_jira_link_not_a_broken_one(tmp_path):
    """A download that raises leaves no file, so the reference must not keep
    pointing at one."""
    att = ExplodingAttachment("diagram.png", size=4096)
    h = handler(tmp_path, None)
    images, others = h.download_attachments(FakeIssue([att]))
    assert images == [] and others == []
    out = h.replace_attachment_references("![](diagram.png)")
    assert out == f"[diagram.png]({BASE}/attachment/diagram.png) (4.0 KB)"


def test_failed_download_is_listed_in_the_attachments_section(tmp_path):
    att = ExplodingAttachment("diagram.png", size=4096)
    h = handler(tmp_path, None)
    images, others = h.download_attachments(FakeIssue([att]))
    md = h.get_attachment_list_markdown(images, others)
    assert f"[diagram.png]({BASE}/attachment/diagram.png) (4.0 KB)" in md


def test_reference_to_an_attachment_jira_no_longer_returns_is_marked(tmp_path):
    """Real data: DAQ-25762 references six images, but fields.attachment is
    empty — they were deleted in Jira. Without a URL the only honest output is
    a marker; a relative link would 404 in GitHub and dangle in Obsidian."""
    h = handler(tmp_path, None)
    h.download_attachments(FakeIssue([]))
    out = h.replace_attachment_references("see ![](image-20260518-105203.png) here")
    assert out == "see *(attachment unavailable: image-20260518-105203.png)* here"


def test_unresolvable_caret_reference_is_marked(tmp_path):
    h = handler(tmp_path, None)
    out = h.replace_attachment_references("see [^SupportArchive3F642709.zip]")
    assert out == "see *(attachment unavailable: SupportArchive3F642709.zip)*"


def test_markdown_footnotes_are_not_mistaken_for_attachments(tmp_path):
    """[^1] is footnote syntax, not a Jira attachment reference."""
    h = handler(tmp_path, None)
    text = "a claim[^1]\n\n[^1]: the note"
    assert h.replace_attachment_references(text) == text


def test_rendered_links_are_not_swept_as_unresolvable(tmp_path):
    """The sweep runs last; it must not touch links this handler just wrote."""
    att = FakeAttachment("flow.png")
    h = handler(tmp_path, None, links=github_at())
    h.download_attachments(FakeIssue([att]))
    out = h.replace_attachment_references("![](flow.png)")
    assert out == "![flow.png](attachments/flow.png)"
    assert "unavailable" not in out


def test_external_image_urls_are_not_swept(tmp_path):
    h = handler(tmp_path, None)
    text = "![](https://example.com/pic.png)"
    assert h.replace_attachment_references(text) == text


# ---------------------------------------------------------------------------
# Regressions found in review (2026-09-28)
# ---------------------------------------------------------------------------

def downloaded(tmp_path, **files):
    """A handler with `files` already recorded as written to disk."""
    h = AttachmentHandler(None, str(tmp_path / "attachments"),
                          links=GithubLinks(BASE, set()).at(Location.ticket("A")))
    h.downloaded_files = dict(files)
    return h


def test_link_form_reference_to_a_downloaded_image_is_not_marked_unavailable(tmp_path):
    """Jira's [^file] macro works for images too. Claiming the file is gone
    while it sits in attachments/ is a lie the export must not tell."""
    h = downloaded(tmp_path, **{"flow.png": "flow.png"})
    out = h.replace_attachment_references("see [^flow.png] here")
    assert "unavailable" not in out
    assert out == "see [flow.png](attachments/flow.png) here"


def test_embed_form_reference_to_a_downloaded_non_image_becomes_a_link(tmp_path):
    """!spec.pdf! cannot be embedded in markdown; render it as a link."""
    h = downloaded(tmp_path, **{"spec.pdf": "spec.pdf"})
    out = h.replace_attachment_references("see !spec.pdf! here")
    assert out == "see [spec.pdf](attachments/spec.pdf) here"


def test_embed_form_reference_to_a_downloaded_image_still_embeds(tmp_path):
    h = downloaded(tmp_path, **{"flow.png": "flow.png"})
    out = h.replace_attachment_references("see ![](flow.png) here")
    assert out == "see ![flow.png](attachments/flow.png) here"


def test_unresolved_sweep_leaves_fenced_code_alone(tmp_path):
    h = downloaded(tmp_path)
    text = "before\n```\n![](secret.png)\n```\nafter"
    assert h.replace_attachment_references(text) == text


def test_unresolved_sweep_leaves_inline_code_alone(tmp_path):
    h = downloaded(tmp_path)
    text = "use `![](secret.png)` verbatim"
    assert h.replace_attachment_references(text) == text


def test_unresolved_sweep_leaves_numeric_footnote_labels_alone(tmp_path):
    """[^RFC.2119] is a footnote, not a filename: its extension has no letter."""
    h = downloaded(tmp_path)
    text = "see [^RFC.2119] and [^1] and [^note]"
    assert h.replace_attachment_references(text) == text


def test_unresolved_sweep_still_marks_a_real_missing_attachment(tmp_path):
    h = downloaded(tmp_path)
    out = h.replace_attachment_references("see [^deleted.png] here")
    assert out == "see *(attachment unavailable: deleted.png)* here"


def test_skipped_attachment_without_a_content_url_is_marked_unavailable(tmp_path):
    """An empty href renders as a link to the current page."""
    h = downloaded(tmp_path)
    h.skipped = [("SupportArchive.zip", "", 11_744_051)]
    md = h.get_attachment_list_markdown([], [])
    assert "]()" not in md
    assert "*(attachment unavailable: SupportArchive.zip)*" in md


def test_reference_to_a_urlless_skipped_attachment_is_marked_unavailable(tmp_path):
    h = downloaded(tmp_path)
    h.skipped = [("SupportArchive.zip", "", 2048)]
    out = h.replace_attachment_references("see [^SupportArchive.zip] here")
    assert "]()" not in out
    assert out == "see *(attachment unavailable: SupportArchive.zip)* here"


def test_bare_caret_reference_to_a_skipped_file_is_rewritten(tmp_path):
    h = downloaded(tmp_path)
    h.skipped = [("SupportArchive.zip", "https://ex.net/att/1", 2048)]
    out = h.replace_attachment_references("see ^SupportArchive.zip here")
    assert out == "see [SupportArchive.zip](https://ex.net/att/1) (2.0 KB) here"


def test_unresolved_sweep_handles_parentheses_in_filenames(tmp_path):
    """Real vault data: SupportArchiveD2DFE639(1).zip. The name pattern
    excluded ')', so this reference escaped both rewriting and the sweep and
    shipped as a literal [^...] in the export."""
    h = downloaded(tmp_path)
    out = h.replace_attachment_references("Attaching: [^SupportArchiveD2DFE639(1).zip]")
    assert out == "Attaching: *(attachment unavailable: SupportArchiveD2DFE639(1).zip)*"


def test_unresolved_sweep_handles_parentheses_in_image_references(tmp_path):
    h = downloaded(tmp_path)
    out = h.replace_attachment_references("see ![](Screenshot(1).png) here")
    assert out == "see *(attachment unavailable: Screenshot(1).png)* here"


def test_unresolved_sweep_does_not_run_together_two_references(tmp_path):
    """The widened name pattern must still stop at whitespace."""
    h = downloaded(tmp_path)
    out = h.replace_attachment_references("![](a.png) and ![](b.png)")
    assert out == (
        "*(attachment unavailable: a.png)* and *(attachment unavailable: b.png)*"
    )


def test_downloaded_reference_inside_code_is_left_verbatim(tmp_path):
    """A description documenting Jira syntax must survive even when the file
    it names was in fact downloaded — the sweep already skips code spans, and
    reference rewriting has to skip them for the same reason."""
    h = downloaded(tmp_path, **{"flow.png": "flow.png"})
    text = "use `![](flow.png)` verbatim\n\n```\n[^flow.png]\n```"
    assert h.replace_attachment_references(text) == text


def test_rewriting_outside_code_still_happens_when_code_is_present(tmp_path):
    h = downloaded(tmp_path, **{"flow.png": "flow.png"})
    out = h.replace_attachment_references("`literal ![](flow.png)` but ![](flow.png) here")
    assert out == "`literal ![](flow.png)` but ![flow.png](attachments/flow.png) here"
