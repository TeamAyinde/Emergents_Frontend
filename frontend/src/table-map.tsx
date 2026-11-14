import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, EventTable } from "./api";
import { canAccess, Level, LEVEL_INFO } from "./levels";
import { colors, radius, spacing } from "./theme";
import { LuxButton } from "./ui";

const SECTION_COLOR: Record<string, string> = { "Main Floor": colors.brandPrimary, VIP: colors.brandSecondary, "Stage Skybox": colors.info };

/** Interactive floor plan: tap a table, see min spend, book it. */
export function TableMap({ eventId, userLevel }: { eventId: string; userLevel: Level }) {
  const qc = useQueryClient();
  const router = useRouter();
  const [sel, setSel] = useState<EventTable | null>(null);
  const [party, setParty] = useState(4);
  const { data: tables } = useQuery({ queryKey: ["tables", eventId], queryFn: () => api.eventTables(eventId) });
  const book = useMutation({
    mutationFn: () => api.bookTable(eventId, sel!.id, party),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["tables", eventId] });
      qc.invalidateQueries({ queryKey: ["mine-tables"] });
    },
  });

  if (!tables || tables.length === 0) return null;
  const fee = sel ? sel.min_spend * LEVEL_INFO[userLevel].fee : 0;
  const locked = sel ? !canAccess(userLevel, sel.min_level) : false;

  return (
    <View style={{ gap: spacing.md }}>
      <Text style={styles.title}>Tables & VIP</Text>
      <View style={styles.map} testID="table-map">
        <View style={styles.stage}><Text style={styles.stageText}>DJ · STAGE</Text></View>
        <View style={styles.bar}><Text style={styles.stageText}>BAR</Text></View>
        {tables.map((t) => {
          const isSel = sel?.id === t.id;
          const c = SECTION_COLOR[t.section] ?? colors.brandPrimary;
          return (
            <Pressable
              key={t.id}
              testID={`table-${t.id}`}
              disabled={t.booked}
              onPress={() => {
                setSel(t);
                setParty(Math.min(4, t.capacity));
                book.reset();
              }}
              style={[
                styles.table,
                t.section === "Stage Skybox" && styles.tableLarge,
                { left: `${t.x}%`, top: `${t.y}%`, borderColor: c },
                isSel && { backgroundColor: c },
                t.booked && styles.booked,
              ]}
            >
              <Text style={[styles.tableText, isSel && { color: colors.surface }]}>{t.booked ? "✕" : t.name}</Text>
            </Pressable>
          );
        })}
      </View>
      <View style={styles.legend}>
        {Object.entries(SECTION_COLOR).map(([k, c]) => (
          <View key={k} style={styles.legendItem}>
            <View style={[styles.dot, { backgroundColor: c }]} />
            <Text style={styles.legendText}>{k}</Text>
          </View>
        ))}
        <View style={styles.legendItem}><Text style={styles.legendText}>✕ Booked</Text></View>
      </View>

      {sel ? (
        <View style={styles.card} testID="table-detail">
          <View style={styles.rowBetween}>
            <Text style={styles.cardTitle}>{sel.section} · {sel.name}</Text>
            <Text style={styles.minSpend}>${sel.min_spend.toFixed(0)} min</Text>
          </View>
          <Text style={styles.muted}>Seats up to {sel.capacity}. Minimum spend goes toward bottles and service on the night.</Text>
          <View style={styles.partyRow}>
            <Text style={styles.label}>Party size</Text>
            <View style={styles.stepper}>
              <Pressable testID="table-party-minus" onPress={() => setParty(Math.max(1, party - 1))} style={styles.stepBtn}>
                <FeatherIcon name="minus" size={16} color={colors.onSurface} />
              </Pressable>
              <Text style={styles.stepVal} testID="table-party-value">{party}</Text>
              <Pressable testID="table-party-plus" onPress={() => setParty(Math.min(sel.capacity, party + 1))} style={styles.stepBtn}>
                <FeatherIcon name="plus" size={16} color={colors.onSurface} />
              </Pressable>
            </View>
          </View>
          <View style={styles.rowBetween}>
            <Text style={styles.muted}>Concierge fee ({Math.round(LEVEL_INFO[userLevel].fee * 100)}%)</Text>
            <Text style={styles.val}>${fee.toFixed(2)}</Text>
          </View>
          <View style={styles.rowBetween}>
            <Text style={styles.cardTitle}>Deposit total</Text>
            <Text style={styles.cardTitle}>${(sel.min_spend + fee).toFixed(2)}</Text>
          </View>
          {book.isSuccess ? <Text style={styles.ok} testID="table-booked-msg">Table {sel.name} is yours. See it in Profile.</Text> : null}
          {book.error ? <Text style={styles.err} testID="table-error">{book.error.message}</Text> : null}
          {locked ? (
            <LuxButton
              testID="table-unlock-btn"
              label={`${LEVEL_INFO[sel.min_level as Level].label} members only · Upgrade`}
              onPress={() => router.push("/membership")}
            />
          ) : !book.isSuccess ? (
            <LuxButton testID="table-book-btn" label={book.isPending ? "Booking…" : "Book this table"} onPress={() => book.mutate()} loading={book.isPending} />
          ) : null}
        </View>
      ) : (
        <Text style={styles.muted}>Tap a table to see its minimum spend.</Text>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  title: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  map: {
    height: 260, borderRadius: radius.lg, backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    overflow: "hidden",
  },
  stage: {
    position: "absolute", top: 12, left: "25%", width: "40%", height: 36, borderRadius: radius.md,
    backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center",
  },
  bar: {
    position: "absolute", top: "30%", left: 12, width: 44, height: 70, borderRadius: radius.md,
    backgroundColor: colors.surfaceTertiary, alignItems: "center", justifyContent: "center",
  },
  stageText: { color: colors.muted, fontSize: 9, fontWeight: "800", letterSpacing: 1.5 },
  table: {
    position: "absolute", width: 44, height: 44, marginLeft: -22, marginTop: -22, borderRadius: 22, borderWidth: 2,
    alignItems: "center", justifyContent: "center", backgroundColor: colors.surface,
  },
  tableLarge: { width: 56, height: 56, marginLeft: -28, marginTop: -28, borderRadius: radius.md },
  booked: { opacity: 0.35, borderStyle: "dashed" },
  tableText: { color: colors.onSurface, fontSize: 12, fontWeight: "800" },
  legend: { flexDirection: "row", flexWrap: "wrap", gap: spacing.md },
  legendItem: { flexDirection: "row", alignItems: "center", gap: 6 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { color: colors.muted, fontSize: 12 },
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.brandPrimary },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  cardTitle: { color: colors.onSurface, fontSize: 16, fontWeight: "800" },
  minSpend: { color: colors.brandPrimary, fontSize: 16, fontWeight: "800" },
  muted: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  val: { color: colors.onSurface, fontSize: 13, fontWeight: "700" },
  label: { color: colors.onSurface, fontSize: 14 },
  partyRow: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  stepper: { flexDirection: "row", alignItems: "center", gap: spacing.md },
  stepBtn: { width: 44, height: 44, borderRadius: 22, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  stepVal: { color: colors.onSurface, fontSize: 18, fontWeight: "800", minWidth: 24, textAlign: "center" },
  ok: { color: colors.success, fontSize: 13 },
  err: { color: colors.error, fontSize: 13 },
});
