import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from "react-native";

import { useAuth } from "./auth-context";
import { colors, radius, spacing } from "./theme";

/** One-tap "Continue with Google" — new Google users join as Bronze guests. */
export function GoogleButton({ testID = "google-signin-btn" }: { testID?: string }) {
  const { signInWithGoogle } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function onPress() {
    setErr("");
    setBusy(true);
    try {
      await signInWithGoogle();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Google sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={{ gap: spacing.xs }}>
      <Pressable testID={testID} onPress={onPress} disabled={busy} style={styles.btn}>
        {busy ? (
          <ActivityIndicator color={colors.onSurface} />
        ) : (
          <>
            <Text style={styles.g}>G</Text>
            <Text style={styles.label}>Continue with Google</Text>
          </>
        )}
      </Pressable>
      {err ? <Text style={styles.err}>{err}</Text> : null}
    </View>
  );
}

export function OrDivider() {
  return (
    <View style={styles.or}>
      <View style={styles.line} />
      <Text style={styles.orText}>or</Text>
      <View style={styles.line} />
    </View>
  );
}

const styles = StyleSheet.create({
  btn: {
    minHeight: 52, borderRadius: radius.pill, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceSecondary, flexDirection: "row", alignItems: "center", justifyContent: "center", gap: spacing.sm,
  },
  g: { color: colors.brandPrimary, fontSize: 18, fontWeight: "900" },
  label: { color: colors.onSurface, fontSize: 16, fontWeight: "700" },
  err: { color: colors.error, fontSize: 13, textAlign: "center" },
  or: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  line: { flex: 1, height: 0.5, backgroundColor: colors.divider },
  orText: { color: colors.muted, fontSize: 12 },
});
