import { LinearGradient } from "expo-linear-gradient";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";

import { LuxButton } from "@/src/ui";
import { GoogleButton } from "@/src/google-button";
import { colors, radius, spacing } from "@/src/theme";

export default function Welcome() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  return (
    <View style={styles.root}>
      <Image
        source="https://images.unsplash.com/photo-1545128485-c400e7702796?crop=entropy&cs=srgb&fm=jpg&w=1400&q=80"
        style={StyleSheet.absoluteFill}
        contentFit="cover"
      />
      <LinearGradient
        colors={["rgba(9,9,11,0.3)", "rgba(9,9,11,0.7)", "rgba(9,9,11,0.98)"]}
        locations={[0, 0.45, 0.95]}
        style={StyleSheet.absoluteFill}
      />
      <View style={[styles.content, { paddingBottom: insets.bottom + spacing.xl, paddingTop: insets.top + spacing.xl }]}>
        <View style={styles.header}>
          <View style={styles.badge}>
            <Text style={styles.badgeText}>MEMBERS CLUB</Text>
          </View>
          <Text style={styles.brand}>Nocturne</Text>
          <Text style={styles.tag}>
            Where nightlife meets hospitality.{"\n"}Events, reservations, and promoter payouts — in one place.
          </Text>
        </View>

        <View style={styles.bottom}>
          <View style={styles.perks}>
            <Perk label="Free for women" />
            <Perk label="1-month free for men" />
            <Perk label="Promoters earn on every guest" />
          </View>
          <GoogleButton testID="welcome-google-btn" />
          <LuxButton
            testID="welcome-signup-btn"
            label="Create your account"
            onPress={() => router.push("/(auth)/sign-up")}
          />
          <Pressable
            testID="welcome-signin-btn"
            onPress={() => router.push("/(auth)/sign-in")}
            style={styles.signInBtn}
          >
            <Text style={styles.signInText}>I already have an account</Text>
          </Pressable>
        </View>
      </View>
    </View>
  );
}

function Perk({ label }: { label: string }) {
  return (
    <View style={styles.perk}>
      <View style={styles.dot} />
      <Text style={styles.perkText}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  content: { flex: 1, justifyContent: "space-between", paddingHorizontal: spacing.xl },
  header: {},
  badge: {
    alignSelf: "flex-start",
    paddingHorizontal: spacing.md,
    paddingVertical: 6,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: colors.brandPrimary,
    marginTop: spacing.lg,
  },
  badgeText: {
    color: colors.brandPrimary,
    fontSize: 11,
    fontWeight: "700",
    letterSpacing: 2,
  },
  brand: {
    color: colors.onSurface,
    fontSize: 56,
    fontWeight: "800",
    letterSpacing: -1,
    marginTop: spacing.lg,
  },
  tag: {
    color: colors.muted,
    fontSize: 15,
    lineHeight: 22,
    marginTop: spacing.sm,
  },
  bottom: { gap: spacing.md },
  perks: { gap: spacing.sm, marginBottom: spacing.sm },
  perk: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  dot: { width: 6, height: 6, borderRadius: 3, backgroundColor: colors.brandPrimary },
  perkText: { color: colors.onSurfaceSecondary, fontSize: 14 },
  signInBtn: { alignItems: "center", paddingVertical: spacing.md },
  signInText: { color: colors.muted, fontSize: 14 },
});
