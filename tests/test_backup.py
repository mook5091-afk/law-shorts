import datetime as dt

from shorts import backup as B

KST = B.KST
NOW = dt.datetime(2026, 11, 22, 12, 0, tzinfo=KST)


def row(pid, yt="", ig="", t="2026-11-20 16:00:00", fmt="quiz", note=""):
    r = [""] * 12
    r[B.C_ID], r[B.C_TITLE], r[B.C_URL] = pid, f"title {pid}", f"https://x.blogspot.com/{pid}.html"
    r[B.C_YT], r[B.C_IG], r[B.C_TIME], r[B.C_FMT], r[B.C_NOTE] = yt, ig, t, fmt, note
    return r


def test_last_primary_ignores_backup_rows():
    rows = [row("A", t="2026-11-20 16:00:00"),
            row("B", t="2026-11-22 11:00:00", fmt=B.BACKUP_FORMAT, note="클라우드 백업")]
    assert B.last_primary_activity(rows) == dt.datetime(2026, 11, 20, 16, 0, tzinfo=KST)


def test_pending_skips_already_uploaded_platforms():
    rows = [row("A", yt="y", ig="i"),            # 완료
            row("B", yt="y"),                    # 인스타만 필요
            row("C"), row("C", fmt="card"),      # 둘 다 필요(같은 글 여러 형식 → 1건)
            row("D", fmt="en:quiz")]             # 영어 채널 제외
    jobs = {j["id"]: j["need"] for j in B.pending_jobs(rows, [])}
    assert jobs == {"B": ["instagram"], "C": ["instagram", "youtube"]}


def test_pending_adds_new_blog_posts_once():
    rows = [row("A", yt="y", ig="i")]
    posts = [{"id": "A", "title": "t", "url": "https://x.blogspot.com/a"},
             {"id": "N", "title": "n", "url": "https://x.blogspot.com/n"}]
    assert [j["id"] for j in B.pending_jobs(rows, posts)] == ["N"]


def test_uploads_today_counts_by_kst_date():
    rows = [row("A", yt="y", ig="i", t="2026-11-22 09:00:00"), row("B", yt="y", t="2026-11-21 23:00:00")]
    assert B.uploads_today(rows, NOW) == (1, 1)


def test_fetch_rejects_non_blogspot_url():
    import pytest
    with pytest.raises(ValueError):
        B.fetch_post_text("http://169.254.169.254/latest")


def test_idle_without_config(monkeypatch):
    for k in ("SHORTS_SHEET_ID", "GEMINI_API_KEY", "YT_REFRESH_TOKEN", "TELEGRAM_BOT_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    assert B.main([]) == 0
