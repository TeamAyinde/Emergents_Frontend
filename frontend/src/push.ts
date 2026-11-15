import AsyncStorage from "@react-native-async-storage/async-storage";
import * as Device from "expo-device";
import * as Linking from "expo-linking";
import * as Notifications from "expo-notifications";
import { Alert, Platform } from "react-native";

import { api } from "./api";

const ASKED_KEY = "pushAskedAt";
const NUDGE_KEY = "pushNudgeAt";
const WEEK = 7 * 24 * 60 * 60 * 1000;

async function register(userId: string) {
  const token = await Notifications.getDevicePushTokenAsync();
  await api.registerPush({ user_id: userId, platform: Platform.OS, device_token: String(token.data) });
}

function ask(title: string, message: string, yes: string): Promise<boolean> {
  return new Promise((resolve) =>
    Alert.alert(title, message, [
      { text: "Not now", style: "cancel", onPress: () => resolve(false) },
      { text: yes, onPress: () => resolve(true) },
    ]),
  );
}

/** Called after sign-in and on every app open. Never blocks the app. */
export async function setupPush(userId: string) {
  if (Platform.OS === "web" || !Device.isDevice) return;
  try {
    const perm = await Notifications.getPermissionsAsync();
    if (perm.status === "granted") return await register(userId);

    if (perm.canAskAgain) {
      const asked = await AsyncStorage.getItem(ASKED_KEY);
      if (asked && Date.now() - Number(asked) < WEEK) return;
      await AsyncStorage.setItem(ASKED_KEY, String(Date.now()));
      const ok = await ask(
        "Stay in the loop",
        "Get a heads-up when you're approved for a guest list, a table is booked, or your concierge replies.",
        "Turn on",
      );
      if (!ok) return;
      const res = await Notifications.requestPermissionsAsync();
      if (res.status === "granted") await register(userId);
      return;
    }

    // Denied for good — gently point to Settings once a week
    const last = await AsyncStorage.getItem(NUDGE_KEY);
    if (last && Date.now() - Number(last) <= WEEK) return;
    const open = await ask(
      "Notifications are off",
      "Turn them on in Settings to hear about guest list approvals, bookings and concierge replies.",
      "Open Settings",
    );
    await AsyncStorage.setItem(NUDGE_KEY, String(Date.now()));
    if (open) Linking.openSettings();
  } catch (e) {
    console.log("push setup skipped", e);
  }
}
