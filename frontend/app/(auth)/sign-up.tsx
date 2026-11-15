import { useLocalSearchParams, useRouter } from "expo-router";
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
import { colors, radius, spacing } from "@/src/theme";
import type { User } from "@/src/api";
import { startCheckout } from "@/src/payments";
import { Level, LEVEL_INFO } from "@/src/levels";

type Role = User["role"];
const ROLES: { value: Exclude<Role, "admin">; label: string; blurb: string }[] = [
  { value: "guest", label: "Guest", blurb: "Buy tickets, book tables, get deals." },
  { value: "promoter", label: "Promoter", blurb: "Earn cash on every guest you bring." },
  { value: "venue_owner", label: "Venue", blurb: "Host events, hire promoters, grow." },
];

const TIERS: { value: string; label: string; blurb: string; price: string }[] = [
  { value: "free_girl", label: "Ladies", blurb: "Bronze is free forever for women.", price: "Bronze free" },
  { value: "trial_male", label: "Gentlemen", blurb: "7 days of Bronze free, then $14.99/month. Cancel anytime.", price: "7 days free" },
  { value: "member", label: "No perk", blurb: "Start paying from day one.", price: "Standard" },
];
const LEVELS: Level[] = ["bronze", "silver", "gold"];

export default function SignUp() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { signUp } = useAuth();
  const [step, setStep] = useState<"role" | "tier" | "form">("role");
  const [role, setRole] = useState<Exclude<Role, "admin">>("guest");
  const [tier, setTier] = useState("trial_male");
  const [level, setLevel] = useState<Level>("bronze");
  const [name, setName] = useState("");
  const params = useLocalSearchParams<{ email?: string }>();
  const [email, setEmail] = useState(typeof params.email === "string" ? params.email : "");
  const [password, setPassword] = useState("");
  const [phone, setPhone] = useState("");
  const [city, setCity] = useState("");
  const [optIn, setOptIn] = useState(true);
  const [invite, setInvite] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit() {
    setErr("");
    if (!name || !email || !password) {
      setErr("Fill all fields");
      return;
    }
    setBusy(true);
    try {
      const membership_tier = role === "venue_owner" ? "venue" : tier;
      await signUp({
        email: email.trim(), password, full_name: name.trim(), role, membership_tier,
        phone: phone.trim() || undefined, city: city.trim() || undefined, marketing_opt_in: optIn,
        invite_code: role === "guest" ? invite.trim() || undefined : undefined,
      });
      // every paid plan is a monthly card subscription; gentlemen get 7 days free before the first charge
      if (role !== "venue_owner" && !(level === "bronze" && tier === "free_girl")) {
        try {
          await startCheckout({ kind: "membership", level }, router);
        } catch {
          router.replace("/membership");
        }
        return;
      }
      router.replace("/(tabs)");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Sign up failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.root}>
      <ScrollView
        contentContainerStyle={[
          styles.content,
          { paddingTop: insets.top + spacing.xl, paddingBottom: insets.bottom + spacing.xl },
        ]}
        keyboardShouldPersistTaps="handled"
      >
        <Pressable testID="back-btn" onPress={() => (step === "role" ? router.back() : setStep(step === "form" ? "tier" : "role"))} style={styles.back}>
          <Text style={styles.backText}>←</Text>
        </Pressable>

        {step === "role" && (
          <>
            <Text style={styles.title}>Who are you tonight?</Text>
            <Text style={styles.subtitle}>{"Pick how you'll use Nocturne."}</Text>
            <View style={styles.cards}>
              {ROLES.map((r) => (
                <Pressable
                  key={r.value}
                  testID={`role-${r.value}`}
                  onPress={() => setRole(r.value)}
                  style={[styles.card, role === r.value && styles.cardSelected]}
                >
                  <Text style={styles.cardTitle}>{r.label}</Text>
                  <Text style={styles.cardBlurb}>{r.blurb}</Text>
                </Pressable>
              ))}
            </View>
            <LuxButton testID="role-next-btn" label="Continue" onPress={() => setStep(role === "venue_owner" ? "form" : "tier")} />
          </>
        )}

        {step === "tier" && (
          <>
            <Text style={styles.title}>Choose your tier</Text>
            <Text style={styles.subtitle}>Gold unlocks the most exclusive venues and services.</Text>
            <View style={styles.cards}>
              {LEVELS.map((l) => {
                const info = LEVEL_INFO[l];
                return (
                  <Pressable
                    key={l}
                    testID={`level-${l}`}
                    onPress={() => setLevel(l)}
                    style={[styles.card, level === l && { borderColor: info.color, backgroundColor: colors.surfaceTertiary }]}
                  >
                    <View style={styles.tierHeader}>
                      <Text style={[styles.cardTitle, { color: info.color }]}>{info.label}</Text>
                      <Text style={styles.price}>${info.price}/mo</Text>
                    </View>
                    <Text style={styles.cardBlurb}>{info.perks.slice(1).join(" · ")}</Text>
                  </Pressable>
                );
              })}
            </View>
            <Text style={styles.label}>Bronze welcome perk</Text>
            <View style={styles.cards}>
              {TIERS.map((t) => (
                <Pressable
                  key={t.value}
                  testID={`tier-${t.value}`}
                  onPress={() => setTier(t.value)}
                  style={[styles.card, tier === t.value && styles.cardSelected]}
                >
                  <View style={styles.tierHeader}>
                    <Text style={styles.cardTitle}>{t.label}</Text>
                    <Text style={styles.price}>{t.price}</Text>
                  </View>
                  <Text style={styles.cardBlurb}>{t.blurb}</Text>
                </Pressable>
              ))}
            </View>
            <LuxButton testID="tier-next-btn" label="Continue" onPress={() => setStep("form")} />
          </>
        )}

        {step === "form" && (
          <>
            <Text style={styles.title}>Create account</Text>
            <Text style={styles.subtitle}>{"We'll keep it short."}</Text>
            <View style={styles.form}>
              <Field label="Full name" testID="signup-name" value={name} onChangeText={setName} />
              <Field label="Email" testID="signup-email" value={email} onChangeText={setEmail} keyboardType="email-address" />
              <Field label="Password" testID="signup-password" value={password} onChangeText={setPassword} secureTextEntry />
              <Field label="Phone (optional)" testID="signup-phone" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
              <Field label="City (optional)" testID="signup-city" value={city} onChangeText={setCity} />
              {role === "guest" ? (
                <Field label="Invite code (optional)" testID="signup-invite" value={invite} onChangeText={(t: string) => setInvite(t.toUpperCase())} />
              ) : null}
              <Pressable testID="signup-optin" accessibilityRole="checkbox" accessibilityState={{ checked: optIn }} onPress={() => setOptIn(!optIn)} style={styles.optin}>
                <View style={[styles.box, optIn && styles.boxOn]}>
                  {optIn ? <Text style={styles.check}>✓</Text> : null}
                </View>
                <Text style={styles.optinText}>
                  Send me the Nocturne Journal, member deals and event invites. Unsubscribe anytime in Profile.
                </Text>
              </Pressable>
              {err ? <Text style={styles.err} testID="signup-error">{err}</Text> : null}
              <LuxButton testID="signup-submit" label={busy ? "Creating…" : "Create account"} onPress={submit} loading={busy} />
            </View>
          </>
        )}

        <Pressable onPress={() => router.replace("/(auth)/sign-in")} style={styles.footer}>
          <Text style={styles.footerText}>
            Have an account? <Text style={styles.footerLink}>Sign in</Text>
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
  cards: { gap: spacing.md, marginTop: spacing.md },
  card: {
    backgroundColor: colors.surfaceSecondary,
    borderRadius: radius.lg,
    padding: spacing.lg,
    borderWidth: 1.5,
    borderColor: colors.border,
  },
  cardSelected: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  cardTitle: { color: colors.onSurface, fontSize: 18, fontWeight: "700" },
  cardBlurb: { color: colors.muted, fontSize: 13, marginTop: 4 },
  tierHeader: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  price: { color: colors.brandPrimary, fontSize: 13, fontWeight: "700" },
  form: { gap: spacing.md, marginTop: spacing.md },
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
  optin: { flexDirection: "row", gap: spacing.md, alignItems: "flex-start", paddingVertical: spacing.xs },
  box: {
    width: 22, height: 22, borderRadius: radius.sm, borderWidth: 1.5, borderColor: colors.borderStrong,
    alignItems: "center", justifyContent: "center", marginTop: 1,
  },
  boxOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  check: { color: colors.onBrandPrimary, fontSize: 14, fontWeight: "800" },
  optinText: { flex: 1, color: colors.onSurfaceSecondary, fontSize: 13, lineHeight: 19 },
  footer: { alignItems: "center", marginTop: spacing.xl },
  footerText: { color: colors.muted, fontSize: 14 },
  footerLink: { color: colors.brandPrimary, fontWeight: "700" },
});
