import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "./api";
import { colors, radius, spacing } from "./theme";

/** Door fallback: find a guest by name or email and check them in when their QR won't scan. */
export function GuestSearch({ eventId }: { eventId: string }) {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  useEffect(() => {
    const t = setTimeout(() => setQ(text.trim()), 300);
    return () => clearTimeout(t);
  }, [text]);
  const { data, isFetching } = useQuery({
    queryKey: ["guest-search", eventId, q],
    queryFn: () => api.searchGuests(eventId, q),
    enabled: q.length >= 2,
  });
  const checkIn = useMutation({
    mutationFn: api.checkInTicket,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["guest-search", eventId] });
      qc.invalidateQueries({ queryKey: ["host-live", eventId] });
    },
  });

  return (
    <View style={styles.card}>
      <Text style={styles.title}>Find a guest</Text>
      <View style={styles.inputWrap}>
        <FeatherIcon name="search" size={16} color={colors.muted} />
        <TextInput
          testID="guest-search-input"
          value={text}
          onChangeText={setText}
          placeholder="Name or email"
          placeholderTextColor={colors.muted}
          autoCapitalize="none"
          autoCorrect={false}
          style={styles.input}
        />
        {isFetching ? <ActivityIndicator size="small" color={colors.brandPrimary} /> : null}
      </View>
      {checkIn.error ? <Text style={styles.err}>{checkIn.error.message}</Text> : null}
      {q.length >= 2 && data && data.length === 0 ? <Text style={styles.muted}>No ticket holders match “{q}”.</Text> : null}
      {(q.length >= 2 ? data ?? [] : []).map((g) => (
        <View key={g.ticket_id} style={styles.row} testID={`guest-hit-${g.ticket_id}`}>
          <View style={{ flex: 1 }}>
            <Text style={styles.name}>{g.name}{g.quantity > 1 ? ` +${g.quantity - 1}` : ""}</Text>
            <Text style={styles.muted} numberOfLines={1}>{g.email} · #{g.ticket_id.slice(0, 8)}</Text>
          </View>
          {g.checked_in ? (
            <Text style={styles.done}>
              In{g.checked_in_at ? ` ${new Date(g.checked_in_at).toLocaleTimeString("en", { hour: "numeric", minute: "2-digit" })}` : ""}
            </Text>
          ) : (
            <Pressable testID={`guest-checkin-${g.ticket_id}`} disabled={checkIn.isPending} onPress={() => checkIn.mutate(g.ticket_id)} style={styles.btn}>
              <Text style={styles.btnText}>Check in</Text>
            </Pressable>
          )}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "800" },
  inputWrap: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm, height: 48, paddingHorizontal: spacing.md,
    borderRadius: radius.md, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border,
  },
  input: { flex: 1, color: colors.onSurface, fontSize: 15, height: 48 },
  row: { flexDirection: "row", alignItems: "center", gap: spacing.md, paddingVertical: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.divider },
  name: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  muted: { color: colors.muted, fontSize: 13 },
  done: { color: colors.success, fontSize: 13, fontWeight: "700" },
  btn: { height: 44, paddingHorizontal: spacing.lg, borderRadius: radius.pill, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  btnText: { color: colors.onBrandPrimary, fontWeight: "800", fontSize: 13 },
  err: { color: colors.error, fontSize: 13 },
});
