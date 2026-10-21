"""Public pages and HTTP metadata tests."""

import re


def test_core_public_pages_render(client):
    for path in ("/", "/about", "/programs", "/how-it-works", "/pricing"):
        response = client.get(path)
        assert response.status_code == 200, f"{path} returned {response.status_code}"


def test_robots_txt_points_to_sitemap(client):
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.mimetype == "text/plain"
    assert b"Sitemap:" in response.data
    assert b"/sitemap.xml" in response.data


def test_sitemap_is_xml_and_has_homepage(client):
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert response.mimetype in {"application/xml", "text/xml"}
    assert b"<urlset" in response.data
    assert b"<loc>" in response.data


def test_missing_page_returns_404(client):
    response = client.get("/this-page-does-not-exist")
    assert response.status_code == 404


def test_response_has_security_headers(client):
    response = client.get("/")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "DENY"
    assert response.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "frame-ancestors 'none'" in response.headers.get("Content-Security-Policy", "")
    assert response.headers.get("X-Request-ID")
