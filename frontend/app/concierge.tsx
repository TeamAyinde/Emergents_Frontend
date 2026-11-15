import { useRouter } from "expo-router";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { ChatView } from "@/src/chat-view";
import { LEVEL_INFO, Level } from "@/src/levels";
import { colors, spacing } from "@/src/theme";

export default function Concierge() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const lvl = (user?.level ?? "bronze") as Level;
  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="concierge-back" onPress={() => router.back()} style={styles.iconBtn}>
          <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
        </Pressable>
        <View style={{ flex: 1 }}>
          <Text style={styles.title}>Concierge</Text>
          <Text style={styles.sub}>
            {lvl === "gold" ? "Gold priority line" : `${LEVEL_INFO[lvl].label} member · Gold members are answered first`}
          </Text>
        </View>
        <Pressable testID="concierge-report" onPress={() => router.push("/support?context=concierge")} style={styles.iconBtn}
          accessibilityLabel="Report a problem">
          <FeatherIcon name="flag" size={18} color={colors.muted} />
        </Pressable>
      </View>
      <ChatView
        load={api.conciergeMessages}
        send={api.sendConcierge}
        mine={(m) => m.sender === "member"}
        placeholder="Tables, jets, villas, rare bottles…"
        emptyText="Your lifestyle manager can arrange anything: tables, yachts, jets, villas, cars, security. Ask away."
        suggestions={["Book me a VIP table this Saturday", "I need a yacht for 12 guests", "Black car to LAX tomorrow"]}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", gap: spacing.md, paddingHorizontal: spacing.lg, paddingBottom: spacing.md,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  iconBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  title: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  sub: { color: colors.brandPrimary, fontSize: 12, marginTop: 2 },
});
