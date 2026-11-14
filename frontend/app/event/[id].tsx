import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

export default function EventDetails() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const [qty, setQty] = useState(1);
  const [code, setCode] = useState("");

  const { data: ev, isLoading } = useQuery({ queryKey: ["event", id], queryFn: () => api.getEvent(id!) });
  const buy = useMutation({
    mutationFn: () => api.purchaseTicket({ event_id: id!, promoter_code: code.trim() || undefined, quantity: qty }),
    onSuccess: (ticket) => {
      qc.invalidateQueries({ queryKey: ["mine-tickets"] });
      qc.invalidateQueries({ queryKey: ["events"] });
      router.replace(`/ticket/${ticket.id}`);
    },
  });

  if (isLoading || !ev) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  const base = ev.price * qty;
  const fee = base * 0.15;
  const total = base + fee;
  const d = new Date(ev.date);

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: 200 }}>
        <View style={styles.hero}>
          <Image source={ev.image_url} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient
            colors={["rgba(9,9,11,0.5)", "transparent", "rgba(9,9,11,1)"]}
            locations={[0, 0.4, 1]}
            style={StyleSheet.absoluteFill}
          />
          <Pressable
            testID="event-back"
            onPress={() => router.back()}
            style={[styles.back, { top: insets.top + spacing.sm }]}
          >
            <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
          </Pressable>
          <View style={styles.heroBottom}>
            <View style={styles.tagsRow}>
              {ev.tags.map((t) => (
                <View key={t} style={styles.tag}>
                  <Text style={styles.tagText}>{t}</Text>
                </View>
              ))}
            </View>
            <Text style={styles.title}>{ev.title}</Text>
            <Text style={styles.venue}>{ev.venue_name} · {ev.city}</Text>
          </View>
        </View>

        <View style={styles.body}>
          <View style={styles.infoRow}>
            <InfoChip icon="calendar" label={d.toLocaleDateString("en", { weekday: "short", month: "short", day: "numeric" })} />
            <InfoChip icon="clock" label={d.toLocaleTimeString("en", { hour: "numeric", minute: "2-digit" })} />
            <InfoChip icon="dollar-sign" label={`From $${ev.price}`} />
          </View>

          <Text style={styles.sectionTitle}>About</Text>
          <Text style={styles.description}>{ev.description}</Text>

          <Text style={styles.sectionTitle}>Quantity</Text>
          <View style={styles.qtyRow}>
            <Pressable testID="qty-minus" onPress={() => setQty(Math.max(1, qty - 1))} style={styles.qtyBtn}>
              <Text style={styles.qtyBtnText}>−</Text>
            </Pressable>
            <Text style={styles.qtyValue} testID="qty-value">{qty}</Text>
            <Pressable testID="qty-plus" onPress={() => setQty(Math.min(8, qty + 1))} style={styles.qtyBtn}>
              <Text style={styles.qtyBtnText}>+</Text>
            </Pressable>
          </View>

          <Text style={styles.sectionTitle}>Promoter code (optional)</Text>
          <TextInput
            testID="promoter-code"
            value={code}
            onChangeText={setCode}
            placeholder="e.g. MARCO1"
            placeholderTextColor={colors.muted}
            autoCapitalize="characters"
            style={styles.input}
          />

          <View style={styles.breakdown}>
            <Row label="Subtotal" value={`$${base.toFixed(2)}`} />
            <Row label="Platform fee (15%)" value={`$${fee.toFixed(2)}`} />
            <View style={styles.sep} />
            <Row label="Total" value={`$${total.toFixed(2)}`} bold />
          </View>
        </View>
      </ScrollView>

      <View style={[styles.sticky, { paddingBottom: insets.bottom + spacing.md }]}>
        {buy.error ? (
          <Text testID="buy-error" style={{ color: colors.error, marginBottom: spacing.sm }}>
            {buy.error.message}
          </Text>
        ) : null}
        <LuxButton
          testID="buy-ticket-btn"
          label={buy.isPending ? "Processing…" : `Buy ticket · $${total.toFixed(2)}`}
          onPress={() => buy.mutate()}
          loading={buy.isPending}
        />
      </View>
    </View>
  );
}

function InfoChip({ icon, label }: { icon: string; label: string }) {
  return (
    <View style={styles.chip}>
      <FeatherIcon name={icon as any} size={13} color={colors.brandPrimary} />
      <Text style={styles.chipText}>{label}</Text>
    </View>
  );
}
function Row({ label, value, bold }: { label: string; value: string; bold?: boolean }) {
  return (
    <View style={styles.rRow}>
      <Text style={[styles.rLabel, bold && styles.rBold]}>{label}</Text>
      <Text style={[styles.rValue, bold && styles.rBold]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  hero: { height: 420 },
  back: {
    position: "absolute", left: spacing.lg, width: 40, height: 40, borderRadius: 20,
    backgroundColor: "rgba(9,9,11,0.5)", alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border,
  },
  heroBottom: { position: "absolute", bottom: spacing.lg, left: spacing.lg, right: spacing.lg },
  tagsRow: { flexDirection: "row", gap: spacing.xs, marginBottom: spacing.sm },
  tag: { backgroundColor: colors.brandSecondary, paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: radius.sm },
  tagText: { color: colors.onBrandSecondary, fontSize: 10, fontWeight: "700", letterSpacing: 0.5 },
  title: { color: colors.onSurface, fontSize: 32, fontWeight: "800", lineHeight: 36 },
  venue: { color: colors.muted, fontSize: 14, marginTop: spacing.xs },
  body: { padding: spacing.lg, gap: spacing.lg },
  infoRow: { flexDirection: "row", gap: spacing.sm, flexWrap: "wrap" },
  chip: {
    flexDirection: "row", alignItems: "center", gap: 6,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    paddingHorizontal: spacing.md, paddingVertical: 8, borderRadius: radius.pill,
  },
  chipText: { color: colors.onSurface, fontSize: 12, fontWeight: "600" },
  sectionTitle: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  description: { color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 22 },
  qtyRow: { flexDirection: "row", alignItems: "center", gap: spacing.xl, alignSelf: "center" },
  qtyBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  qtyBtnText: { color: colors.onSurface, fontSize: 22, fontWeight: "700" },
  qtyValue: { color: colors.onSurface, fontSize: 28, fontWeight: "800", minWidth: 40, textAlign: "center" },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14,
    color: colors.onSurface, fontSize: 16,
  },
  breakdown: {
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg,
    borderWidth: 1, borderColor: colors.border, gap: spacing.sm,
  },
  rRow: { flexDirection: "row", justifyContent: "space-between" },
  rLabel: { color: colors.muted, fontSize: 14 },
  rValue: { color: colors.onSurface, fontSize: 14 },
  rBold: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  sep: { height: 0.5, backgroundColor: colors.divider, marginVertical: spacing.xs },
  sticky: {
    position: "absolute", left: 0, right: 0, bottom: 0,
    backgroundColor: "rgba(9,9,11,0.95)", borderTopWidth: 1, borderTopColor: colors.border,
    padding: spacing.lg,
  },
});
