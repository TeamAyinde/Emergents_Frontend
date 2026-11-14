import { QueryClientProvider } from "@tanstack/react-query";
import { Stack, useRouter, useSegments } from "expo-router";
import { useEffect } from "react";
import { LogBox, StyleSheet, View, ActivityIndicator, Image } from "react-native";
import { GestureHandlerRootView } from "react-native-gesture-handler";
import { KeyboardProvider } from "react-native-keyboard-controller";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { StatusBar } from "expo-status-bar";

import { ErrorBoundary } from "@/src/components/error-boundary";
import { queryClient } from "@/src/query-client";
import { AuthProvider, useAuth } from "@/src/auth-context";
import { colors } from "@/src/theme";

LogBox.ignoreAllLogs(true);

// Preload icon assets so Expo Go renders them on cold start.
try {
  Image.resolveAssetSource(require("../assets/images/icon.png"));
} catch {}

function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const segments = useSegments();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    const inAuth = segments[0] === "(auth)";
    if (!user && !inAuth) {
      router.replace("/(auth)/welcome");
    } else if (user && inAuth) {
      router.replace("/(tabs)");
    }
  }, [user, loading, segments, router]);

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
