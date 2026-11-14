import { StyleSheet, Text, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { radius, spacing } from "./theme";

export type Level = "bronze" | "silver" | "gold";

// Metal colors are brand constants; identical in every theme.
export const LEVEL_INFO: Record<Level, { label: string; price: number; fee: number; discount: number; color: string; perks: string[] }> = {
  bronze: {
    label: "Bronze", price: 14.99, fee: 0.25, discount: 0, color: "#CD7F32",
    perks: ["Member deals & guest list", "Book tables, hotels & black cars", "25% concierge fee"],
  },
  silver: {
    label: "Silver", price: 49, fee: 0.2, discount: 0.1, color: "#C9CDD3",
    perks: ["Everything in Bronze", "Silver venues, limos, yachts & mansions", "10% off tickets · 20% concierge fee"],
  },
  gold: {
    label: "Gold", price: 149, fee: 0.15, discount: 0.2, color: "#E5A93C",
    perks: ["Everything in Silver", "Most exclusive clubs, jets & superyachts", "20% off tickets · 15% concierge fee"],
  },
};

const RANK: Record<Level, number> = { bronze: 0, silver: 1, gold: 2 };

export function canAccess(userLevel: string | undefined, min: string | undefined) {
  return RANK[(userLevel as Level) ?? "bronze"] >= RANK[(min as Level) ?? "bronze"];
}

export function LevelBadge({ level, floating }: { level?: string; floating?: boolean }) {
  if (!level || level === "bronze") return null;
  const info = LEVEL_INFO[level as Level];
  return (
    <View style={[styles.badge, { borderColor: info.color }, floating && styles.floating]}>
      <FeatherIcon name="lock" size={10} color={info.color} />
      <Text style={[styles.text, { color: info.color }]}>{info.label.toUpperCase()}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    flexDirection: "row", alignItems: "center", gap: 4, paddingHorizontal: spacing.sm, paddingVertical: 3,
    borderRadius: radius.pill, borderWidth: 1, backgroundColor: "rgba(9,9,11,0.75)", alignSelf: "flex-start",
  },
  floating: { position: "absolute", top: spacing.sm, right: spacing.sm },
  text: { fontSize: 10, fontWeight: "800", letterSpacing: 1 },
});
