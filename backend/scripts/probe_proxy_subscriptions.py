"""Probe: which Stripe subscription endpoints the Emergent test proxy supports (iteration 10 RCA)."""
import sys
import certifi
import stripe

stripe.api_key = "sk_test_emergent"
stripe.api_base = "https://integrations.emergentagent.com/stripe"
stripe.ca_bundle_path = certifi.where()
sid = sys.argv[1]
s = stripe.checkout.Session.retrieve(sid)
print("session status", s.get("status"), s.get("payment_status"), "sub", s.get("subscription"), "cust", s.get("customer"))
sub_id = s.get("subscription")
for label, fn in [
    ("Session expand subscription", lambda: stripe.checkout.Session.retrieve(sid, expand=["subscription"]).get("subscription")),
    ("Subscription.retrieve", lambda: stripe.Subscription.retrieve(sub_id)),
    ("Subscription.list(customer)", lambda: stripe.Subscription.list(customer=s.get("customer"), limit=1)),
    ("Subscription.modify (no-op metadata)", lambda: stripe.Subscription.modify(sub_id, metadata={"probe": "1"})),
]:
    try:
        r = fn()
        print("OK  ", label, type(r).__name__, (r.get("status") if hasattr(r, "get") and not isinstance(r, str) else r))
    except Exception as e:
        print("FAIL", label, type(e).__name__, str(e)[:150])
