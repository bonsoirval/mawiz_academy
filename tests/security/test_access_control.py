"""Authorization and response-hardening regression tests."""

def test_admin_dashboard_requires_authentication(client):
    response = client.get("/admin/")
    assert response.status_code in {302, 401, 403}


def test_admin_payments_requires_admin_role(client, login_as, learner_id):
    login_as(learner_id)
    response = client.get("/admin/payments")
    assert response.status_code in {302, 403}


def test_admin_can_access_payment_management(client, login_as, admin_id):
    login_as(admin_id)
    response = client.get("/admin/payments")
    assert response.status_code == 200
    assert b"Course payments" in response.data


def test_request_id_header_is_added(client):
    response = client.get("/", headers={"X-Request-ID": "test-request-123"})
    assert response.headers.get("X-Request-ID") == "test-request-123"


def test_invalid_request_id_is_replaced(client):
    response = client.get("/", headers={"X-Request-ID": "bad request!"})
    assert response.headers.get("X-Request-ID") != "bad request!"
    assert response.headers.get("X-Request-ID")
