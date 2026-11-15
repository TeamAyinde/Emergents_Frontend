import * as WebBrowser from "expo-web-browser";

export const LEGAL_URLS = {
  privacy: `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/legal/privacy`,
  support: `${process.env.EXPO_PUBLIC_BACKEND_URL}/api/legal/support`,
};

/** Opens the hosted privacy policy / support page in an in-app browser. */
export function openLegal(page: keyof typeof LEGAL_URLS) {
  return WebBrowser.openBrowserAsync(LEGAL_URLS[page]);
}
