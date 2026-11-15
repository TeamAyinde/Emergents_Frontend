import { useQuery } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import QRCode from "react-native-qrcode-svg";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { TableUpsell } from "@/src/table-upsell";
import { colors, radius, spacing } from "@/src/theme";

export default function TicketScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data: tickets, isLoading } = useQuery({ queryKey: ["mine-tickets"], queryFn: () => api.myTickets() });
  const ticket = tickets?.find((t) => t.id === id);

  if (isLoading || !ticket) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  const d = new Date(ticket.event_date);
  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{
        paddingTop: insets.top + spacing.md,
        paddingBottom: insets.bottom + spacing.xl,
        paddingHorizontal: spacing.lg,
        gap: spacing.lg,
      }}>
        <View style={styles.headerBar}>
          <Pressable testID="ticket-close" onPress={() => router.back()} style={styles.closeBtn}>
            <FeatherIcon name="x" size={22} color={colors.onSurface} />
          </Pressable>
          <Text style={styles.headerTitle}>Your Ticket</Text>
          <View style={{ width: 40 }} />
        </View>

        <TableUpsell ticket={ticket} />

        <View style={styles.ticketCard}>
          <View style={styles.cardHead}>
            <Text style={styles.eyebrow}>NOCTURNE</Text>
            <Text style={styles.title}>{ticket.event_title}</Text>
            <Text style={styles.sub}>{ticket.venue_name}</Text>
          </View>

          <View style={styles.ticketDivider}>
            <View style={styles.notch} />
            <View style={styles.dashLine} />
            <View style={styles.notch} />
          </View>

          <View style={styles.qrWrap}>
            <View style={styles.qrBox}>
              <QRCode value={ticket.id} size={180} backgroundColor="#ffffff" color="#000000" />
            </View>
            <Text style={styles.ticketId} testID="ticket-id">#{ticket.id.slice(0, 8).toUpperCase()}</Text>
          </View>

          <View style={styles.rowGrid}>
            <Cell label="Date" value={d.toLocaleDateString("en", { month: "short", day: "numeric", year: "numeric" })} />
            <Cell label="Time" value={d.toLocaleTimeString("en", { hour: "numeric", minute: "2-digit" })} />
            <Cell label="Qty" value={`${ticket.quantity}`} />
            <Cell label="Paid" value={`$${ticket.total_paid.toFixed(2)}`} />
          </View>

          <View style={[styles.statusWrap, ticket.checked_in && { backgroundColor: colors.surfaceTertiary }]}>
            <Text style={[styles.statusText, ticket.checked_in && { color: colors.muted }]}>
              {ticket.checked_in ? "CHECKED IN" : "VALID · Show at the door"}
            </Text>
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.cell}>
      <Text style={styles.cellLabel}>{label}</Text>
      <Text style={styles.cellValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  headerBar: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  closeBtn: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  headerTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  ticketCard: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg,
    borderWidth: 1, borderColor: colors.brandPrimary, overflow: "hidden",
  },
  cardHead: { padding: spacing.xl, alignItems: "center", gap: 4 },
  eyebrow: { color: colors.brandPrimary, fontSize: 11, letterSpacing: 3, fontWeight: "800" },
  title: { color: colors.onSurface, fontSize: 22, fontWeight: "800", textAlign: "center" },
  sub: { color: colors.muted, fontSize: 13 },
  ticketDivider: { flexDirection: "row", alignItems: "center" },
  notch: { width: 24, height: 24, borderRadius: 12, backgroundColor: colors.surface, marginHorizontal: -12 },
  dashLine: { flex: 1, borderBottomWidth: 1, borderBottomColor: colors.border, borderStyle: "dashed" },
  qrWrap: { alignItems: "center", gap: spacing.md, paddingVertical: spacing.xl },
  qrBox: { padding: spacing.md, backgroundColor: "#fff", borderRadius: radius.md },
  ticketId: { color: colors.brandPrimary, fontSize: 14, letterSpacing: 2, fontWeight: "700" },
  rowGrid: { flexDirection: "row", flexWrap: "wrap", paddingHorizontal: spacing.lg, paddingBottom: spacing.lg },
  cell: { width: "50%", paddingVertical: spacing.sm },
  cellLabel: { color: colors.muted, fontSize: 10, letterSpacing: 1.5, fontWeight: "700" },
  cellValue: { color: colors.onSurface, fontSize: 15, fontWeight: "700", marginTop: 2 },
  statusWrap: {
    backgroundColor: colors.brandPrimary, paddingVertical: spacing.md, alignItems: "center",
  },
  statusText: { color: colors.onBrandPrimary, fontSize: 13, letterSpacing: 2, fontWeight: "800" },
});
