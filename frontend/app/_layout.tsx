import { QueryClientProvider } from "@tanstack/react-query";
import { Stack, usePathname, useRouter, useSegments } from "expo-router";
import { useEffect } from "react";
import { LogBox, Platform, StyleSheet, View, ActivityIndicator, Image } from "react-native";
import * as Linking from "expo-linking";
import * as Notifications from "expo-notifications";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { AuthProvider, useAuth } from "@/src/auth-context";
import { colors } from "@/src/theme";
import { setupPush } from "@/src/push";

LogBox.ignoreAllLogs(true);

// Foreground display + Android channel must exist before any push arrives
if (Platform.OS !== "web") {
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowAlert: true,
      shouldShowBanner: true,
      shouldShowList: true,
      shouldPlaySound: true,
      shouldSetBadge: false,
    }),
  });
}
if (Platform.OS === "android") {
  Notifications.setNotificationChannelAsync("default", {
    name: "Default",
    importance: Notifications.AndroidImportance.MAX,
    sound: "default",
  });
}

function urlFrom(response: Notifications.NotificationResponse | null): string | null {
  const data = (response?.notification.request.content.data || {}) as Record<string, unknown>;
  const url = data.deeplink || data.action_url;
  return typeof url === "string" && url ? url : null;
}

// Preload icon assets so Expo Go renders them on cold start.
try {
  Image.resolveAssetSource(require("../assets/images/icon.png"));
} catch {}

let pendingPath: string | null = null; // deep link opened while signed out (e.g. feedback email)

function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const segments = useSegments();
  const pathname = usePathname();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    const inAuth = segments[0] === "(auth)";
    if (!user && !inAuth) {
      if (pathname && pathname !== "/" && !pathname.startsWith("/payment-result")) pendingPath = pathname;
      router.replace("/(auth)/welcome");
    } else if (user && inAuth) {
      const next = pendingPath;
      pendingPath = null;
      router.replace((next ?? "/(tabs)") as any);
    }
  }, [user, loading, segments, pathname, router]);

  // Register this device for pushes after sign-in / on every open (tokens rotate)
  const userId = user?.id;
  useEffect(() => {
    if (userId) setupPush(userId);
  }, [userId]);

  // Tapping a notification opens the screen it points to
  useEffect(() => {
    if (Platform.OS === "web") return;
    const open = (url: string | null) => {
      if (!url) return;
      if (url.startsWith("http")) Linking.openURL(url);
      else router.push(url as any);
    };
    const sub = Notifications.addNotificationResponseReceivedListener((r) => open(urlFrom(r)));
    Notifications.getLastNotificationResponseAsync().then((r) => open(urlFrom(r)));
    return () => sub.remove();
  }, [router]);

  if (loading) {
    return (
      <View style={styles.splash}>
        <ActivityIndicator color={colors.brandPrimary} size="large" />
      </View>
    );
  }
  return <>{children}</>;
}

export default function RootLayout() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <SafeAreaProvider>
        <ErrorBoundary>
          <QueryClientProvider client={queryClient}>
            <KeyboardProvider>
              <AuthProvider>
                <StatusBar style="light" />
                <AuthGate>
                  <Stack
                    screenOptions={{
                      headerShown: false,
                      contentStyle: { backgroundColor: colors.surface },
                      animation: "fade",
                    }}
                  >
                    <Stack.Screen name="(auth)" />
                    <Stack.Screen name="(tabs)" />
                    <Stack.Screen name="event/[id]" options={{ animation: "slide_from_right" }} />
                    <Stack.Screen name="venue/[id]" options={{ animation: "slide_from_right" }} />
                    <Stack.Screen name="ticket/[id]" options={{ animation: "slide_from_bottom", presentation: "modal" }} />
                    <Stack.Screen name="checkin" options={{ animation: "slide_from_bottom", presentation: "modal" }} />
                    <Stack.Screen name="payment-result" options={{ animation: "fade", gestureEnabled: false }} />
                    <Stack.Screen name="payout-settings" />
                    <Stack.Screen name="gifts" />
                    <Stack.Screen name="email-settings" />
                    <Stack.Screen name="feedback/[id]" />
                  </Stack>
                </AuthGate>
              </AuthProvider>
            </KeyboardProvider>
          </QueryClientProvider>
        </ErrorBoundary>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  splash: { flex: 1, alignItems: "center", justifyContent: "center", backgroundColor: colors.surface },
});
