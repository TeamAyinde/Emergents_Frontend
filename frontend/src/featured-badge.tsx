import { StyleSheet, Text, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { colors, radius, spacing } from "./theme";

/** Gold "Featured" pill for venues that bought a boost. */
export function FeaturedBadge({ testID, label = "FEATURED" }: { testID?: string; label?: string }) {
  return (
    <View style={styles.pill} testID={testID}>
      <FeatherIcon name="zap" size={10} color={colors.onBrandPrimary} />
      <Text style={styles.text}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  pill: {
    flexDirection: "row", alignItems: "center", gap: 4, alignSelf: "flex-start",
    backgroundColor: colors.brandPrimary, borderRadius: radius.pill, paddingHorizontal: spacing.sm, paddingVertical: 3,
  },
  text: { color: colors.onBrandPrimary, fontSize: 9, fontWeight: "900", letterSpacing: 1 },
});
