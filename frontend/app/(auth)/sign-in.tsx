import { useRouter } from "expo-router";
import { useState } from "react";
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { useAuth } from "@/src/auth-context";
import { LuxButton } from "@/src/ui";
import { GoogleButton, OrDivider } from "@/src/google-button";
import { colors, radius, spacing } from "@/src/theme";

export default function SignIn() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { signIn } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setErr("");
    setBusy(true);
    try {
      await signIn(email.trim(), password);
      router.replace("/(tabs)");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Login failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : "height"}
      style={styles.root}
    >
      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <Pressable testID="back-btn" onPress={() => router.back()} style={styles.back}>
          <Text style={styles.backText}>←</Text>
        </Pressable>
        <Text style={styles.title}>Welcome back</Text>
        <Text style={styles.subtitle}>Sign in to continue your night.</Text>

        <View style={styles.form}>
          <GoogleButton />
          <OrDivider />
          <Field label="Email" testID="signin-email" value={email} onChangeText={setEmail} keyboardType="email-address" />
          <Field label="Password" testID="signin-password" value={password} onChangeText={setPassword} secureTextEntry />
          {err ? <Text style={styles.err} testID="signin-error">{err}</Text> : null}
          <LuxButton testID="signin-submit" label={busy ? "Signing in…" : "Sign in"} onPress={submit} loading={busy} />
        </View>

        <Pressable onPress={() => router.replace("/(auth)/sign-up")} style={styles.footer}>
          <Text style={styles.footerText}>
            New to Nocturne? <Text style={styles.footerLink}>Create account</Text>
          </Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Field({
  label,
  testID,
  value,
  onChangeText,
  secureTextEntry,
  keyboardType,
}: {
  label: string;
  testID: string;
  value: string;
  onChangeText: (v: string) => void;
  secureTextEntry?: boolean;
  keyboardType?: any;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        testID={testID}
        value={value}
        onChangeText={onChangeText}
        secureTextEntry={secureTextEntry}
        keyboardType={keyboardType}
        autoCapitalize="none"
        autoCorrect={false}
        placeholderTextColor={colors.muted}
        style={styles.input}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  content: { paddingHorizontal: spacing.xl, gap: spacing.lg },
  back: { width: 40, height: 40, alignItems: "center", justifyContent: "center" },
  backText: { color: colors.onSurface, fontSize: 24 },
  title: { color: colors.onSurface, fontSize: 32, fontWeight: "800", marginTop: spacing.md },
  subtitle: { color: colors.muted, fontSize: 15, marginTop: -spacing.sm },
  form: { gap: spacing.md, marginTop: spacing.lg },
  field: { gap: spacing.xs },
  label: { color: colors.muted, fontSize: 12, letterSpacing: 1, textTransform: "uppercase" },
  input: {
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radius.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
    color: colors.onSurface,
    fontSize: 16,
  },
  err: { color: colors.error, fontSize: 13 },
  footer: { alignItems: "center", marginTop: spacing.xl },
  footerText: { color: colors.muted, fontSize: 14 },
  footerLink: { color: colors.brandPrimary, fontWeight: "700" },
});
