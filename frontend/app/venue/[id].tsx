import { useMutation, useQuery } from "@tanstack/react-query";
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
import { useAuth } from "@/src/auth-context";
import { canAccess, Level, LEVEL_INFO } from "@/src/levels";
import { startCheckout } from "@/src/payments";

const SERVICES = [
  { v: "table", label: "Table", price: 200 },
  { v: "booth", label: "Booth", price: 400 },
  { v: "bottle", label: "Bottle Service", price: 800 },
];

export default function VenueDetails() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const [service, setService] = useState(SERVICES[0]);
  const [party, setParty] = useState("4");
  const [notes, setNotes] = useState("");
  const { user } = useAuth();
  const lvl = (user?.level ?? "bronze") as Level;
  const nights = Array.from({ length: 7 }, (_, i) => {
    const d = new Date();
    d.setDate(d.getDate() + i + 1);
    d.setHours(21, 0, 0, 0);
    return d;
  });
  const [night, setNight] = useState(0);

  const { data: v, isLoading } = useQuery({ queryKey: ["venue", id], queryFn: () => api.getVenue(id!) });
  const book = useMutation({
    mutationFn: () =>
      startCheckout(
        {
          kind: "reservation",
          venue_id: id!,
          date: nights[night].toISOString(),
          party_size: parseInt(party || "1", 10),
          service_type: service.v,
          notes,
        },
        router,
      ),
  });

  if (isLoading || !v) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  const fee = service.price * LEVEL_INFO[lvl].fee;
  const locked = !canAccess(lvl, v.min_level);
  const total = service.price + fee;

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: 160 }}>
        <View style={styles.hero}>
          <Image source={v.image_url} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient
            colors={["rgba(9,9,11,0.5)", "transparent", "rgba(9,9,11,1)"]}
            locations={[0, 0.4, 1]}
            style={StyleSheet.absoluteFill}
          />
          <Pressable
            testID="venue-back"
            onPress={() => router.back()}
            style={[styles.back, { top: insets.top + spacing.sm }]}
          >
            <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
          </Pressable>
          <View style={styles.heroBottom}>
            <Text style={styles.cat}>{v.category.toUpperCase()}</Text>
            <Text style={styles.name}>{v.name}</Text>
            <View style={styles.metaRow}>
              <FeatherIcon name="map-pin" size={13} color={colors.muted} />
              <Text style={styles.meta}>{v.city}, {v.state}</Text>
              <Text style={styles.metaDot}>·</Text>
              <FeatherIcon name="star" size={13} color={colors.brandPrimary} />
              <Text style={styles.meta} testID="venue-guest-rating">
                {(v.guest_rating ?? v.rating).toFixed(1)}
                {v.guest_rating_count ? ` · ${v.guest_rating_count} guest rating${v.guest_rating_count === 1 ? "" : "s"}` : ""}
              </Text>
              <Text style={styles.metaDot}>·</Text>
              <Text style={styles.meta}>{v.price_range}</Text>
            </View>
          </View>
        </View>

        <View style={styles.body}>
          <Text style={styles.sectionTitle}>About the venue</Text>
          <Text style={styles.description}>{v.description}</Text>

          <Text style={styles.sectionTitle}>Reserve</Text>
          <View style={styles.servicesRow}>
            {SERVICES.map((s) => (
              <Pressable
                key={s.v}
                testID={`service-${s.v}`}
                onPress={() => setService(s)}
                style={[styles.service, service.v === s.v && styles.serviceSelected]}
              >
                <Text style={[styles.serviceLabel, service.v === s.v && { color: colors.onBrandTertiary }]}>
                  {s.label}
                </Text>
                <Text style={[styles.servicePrice, service.v === s.v && { color: colors.brandPrimary }]}>
                  ${s.price}
                </Text>
              </Pressable>
            ))}
          </View>

          <Text style={styles.sectionTitle}>Night</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: spacing.sm }}>
            {nights.map((d, i) => (
              <Pressable
                key={i}
                testID={`night-${i}`}
                onPress={() => setNight(i)}
                style={[styles.night, night === i && styles.serviceSelected]}
              >
                <Text style={styles.nightDow}>{d.toLocaleDateString("en", { weekday: "short" }).toUpperCase()}</Text>
                <Text style={[styles.nightDay, night === i && { color: colors.brandPrimary }]}>{d.getDate()}</Text>
              </Pressable>
            ))}
          </ScrollView>

          <Text style={styles.sectionTitle}>Party size</Text>
          <TextInput
            testID="party-size"
            value={party}
            onChangeText={setParty}
            keyboardType="number-pad"
            style={styles.input}
          />

          <Text style={styles.sectionTitle}>Notes</Text>
          <TextInput
            testID="res-notes"
            value={notes}
            onChangeText={setNotes}
            placeholder="Allergies, celebration, VIP requests…"
            placeholderTextColor={colors.muted}
            multiline
            style={[styles.input, { minHeight: 80 }]}
          />

          <View style={styles.breakdown}>
            <Row label="Base" value={`$${service.price.toFixed(2)}`} />
            <Row label={`Concierge fee (${LEVEL_INFO[lvl].label} ${Math.round(LEVEL_INFO[lvl].fee * 100)}%)`} value={`$${fee.toFixed(2)}`} />
            <View style={styles.sep} />
            <Row label="Total deposit" value={`$${total.toFixed(2)}`} bold />
          </View>
        </View>
      </ScrollView>

      <View style={[styles.sticky, { paddingBottom: insets.bottom + spacing.md }]}>
        {book.error ? (
          <Text testID="reservation-error" style={{ color: colors.error, marginBottom: spacing.sm }}>
            {book.error.message}
          </Text>
        ) : null}
        {locked ? (
          <LuxButton
            testID="unlock-venue-btn"
            label={`${LEVEL_INFO[v.min_level as Level].label} members only · Upgrade`}
            onPress={() => router.push("/membership")}
          />
        ) : (
        <LuxButton
          testID="confirm-reservation-btn"
          label={book.isPending ? "Opening checkout…" : `Pay deposit · $${total.toFixed(2)}`}
          onPress={() => book.mutate()}
          loading={book.isPending}
        />
        )}
      </View>
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
  hero: { height: 380 },
  back: {
    position: "absolute", left: spacing.lg, width: 40, height: 40, borderRadius: 20,
    backgroundColor: "rgba(9,9,11,0.5)", alignItems: "center", justifyContent: "center",
    borderWidth: 1, borderColor: colors.border,
  },
  heroBottom: { position: "absolute", bottom: spacing.lg, left: spacing.lg, right: spacing.lg },
  cat: { color: colors.brandPrimary, fontSize: 11, letterSpacing: 2, fontWeight: "700" },
  name: { color: colors.onSurface, fontSize: 34, fontWeight: "800", marginTop: 6 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: spacing.xs },
  meta: { color: colors.muted, fontSize: 13 },
  metaDot: { color: colors.muted, marginHorizontal: 2 },
  body: { padding: spacing.lg, gap: spacing.lg },
  sectionTitle: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  description: { color: colors.onSurfaceSecondary, fontSize: 14, lineHeight: 22 },
  servicesRow: { flexDirection: "row", gap: spacing.sm },
  service: {
    flex: 1, backgroundColor: colors.surfaceSecondary, borderWidth: 1.5, borderColor: colors.border,
    borderRadius: radius.lg, padding: spacing.md, alignItems: "center", gap: 4,
  },
  serviceSelected: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  night: {
    flexShrink: 0, width: 56, height: 64, borderRadius: radius.md, borderWidth: 1.5,
    borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    alignItems: "center", justifyContent: "center",
  },
  nightDow: { color: colors.muted, fontSize: 10, fontWeight: "700", letterSpacing: 1 },
  nightDay: { color: colors.onSurface, fontSize: 20, fontWeight: "800" },
  serviceLabel: { color: colors.onSurface, fontSize: 14, fontWeight: "700" },
  servicePrice: { color: colors.muted, fontSize: 12 },
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
