import * as Linking from "expo-linking";
import type { Router } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { Platform } from "react-native";

import { api, CheckoutBody } from "./api";

/**
 * Opens Stripe Checkout for a ticket, table, reservation or membership.
 * Web: leaves the app and Stripe brings the guest back to /payment-result.
 * Phone: opens a secure in-app browser, then shows /payment-result.
 */
export async function startCheckout(body: CheckoutBody, router: Router) {
  if (Platform.OS === "web") {
    const res = await api.checkout({ ...body, origin_url: window.location.origin });
    if (res.paid_with_credit || !res.url) {
      router.push(`/payment-result?session_id=${res.session_id}`);
      return;
    }
    window.location.href = res.url;
    return;
  }
  const returnUrl = Linking.createURL("payment-result");
  const res = await api.checkout({
    ...body,
    origin_url: process.env.EXPO_PUBLIC_BACKEND_URL as string,
    return_url: returnUrl,
  });
  if (res.url) await WebBrowser.openAuthSessionAsync(res.url, returnUrl);
  router.push(`/payment-result?session_id=${res.session_id}`);
}
