import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Alert, Platform, Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, Venue } from "./api";
import { colors, radius, spacing } from "./theme";

/** Host Studio: invite door staff who can scan tickets and see the live counter for one venue. */
export function DoorStaffCard({ venues }: { venues: Venue[] }) {
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [venueId, setVenueId] = useState<string | null>(null);
  const venue = venueId ?? venues[0]?.id;
  const { data: staff } = useQuery({ queryKey: ["door-staff"], queryFn: api.doorStaff });
  const add = useMutation({
    mutationFn: () => api.addDoorStaff(venue!, email.trim()),
    onSuccess: () => {
      setEmail("");
      qc.invalidateQueries({ queryKey: ["door-staff"] });
    },
  });
  const schedule = useMutation({
    mutationFn: ({ id, every }: { id: string; every: boolean }) => api.setEveryNight(id, every),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["door-staff"] }),
  });
  const remove = useMutation({
    mutationFn: api.removeDoorStaff,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["door-staff"] }),
  });
  if (!venues.length) return null;

  const confirmRemove = (id: string, name: string) => {
    const msg = `${name} will no longer be able to scan tickets.`;
    if (Platform.OS === "web") {
      if (window.confirm(`Remove from door team?\n${msg}`)) remove.mutate(id);
      return;
    }
    Alert.alert("Remove from door team?", msg, [
      { text: "Cancel", style: "cancel" },
      { text: "Remove", style: "destructive", onPress: () => remove.mutate(id) },
    ]);
  };

  return (
    <View style={styles.card} testID="door-staff-card">
      <Text style={styles.title}>Door staff</Text>
      <Text style={styles.sub}>Invite anyone by email; new people get a sign-up link. Staff scan tickets and see the live counter. Assign shifts on each event.</Text>
      {venues.length > 1 ? (
        <View style={styles.chips}>
          {venues.map((v) => (
            <Pressable key={v.id} testID={`staff-venue-${v.id}`} onPress={() => setVenueId(v.id)} style={[styles.chip, venue === v.id && styles.chipOn]}>
              <Text style={[styles.chipText, venue === v.id && styles.chipTextOn]} numberOfLines={1}>{v.name}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}
      <View style={styles.inputRow}>
        <TextInput
          testID="staff-email-input"
          value={email}
          onChangeText={setEmail}
          placeholder="staff@email.com"
          placeholderTextColor={colors.muted}
          autoCapitalize="none"
          keyboardType="email-address"
          style={styles.input}
        />
        <Pressable testID="staff-invite-btn" disabled={!email.trim() || add.isPending} onPress={() => add.mutate()}
          style={[styles.invite, (!email.trim() || add.isPending) && { opacity: 0.5 }]}>
          <Text style={styles.inviteText}>Invite</Text>
        </Pressable>
      </View>
      {add.error ? <Text style={styles.err}>{add.error.message}</Text> : null}
      {(staff ?? []).map((s) => (
        <View key={s.id} style={styles.row} testID={`staff-row-${s.id}`}>
          <View style={{ flex: 1 }}>
            <View style={styles.nameRow}>
              <Text style={styles.name} numberOfLines={1}>{s.status === "invited" ? s.email : s.name}</Text>
              {s.status === "invited" ? <Text style={styles.badge} testID={`staff-invited-${s.id}`}>Invited</Text> : null}
            </View>
            <Text style={styles.sub} numberOfLines={1}>{s.status === "invited" ? `Sign-up link sent · ${s.venue_name}` : `${s.email} · ${s.venue_name}`}</Text>
            <Pressable testID={`staff-schedule-${s.id}`} onPress={() => schedule.mutate({ id: s.id, every: !s.every_night })} hitSlop={6}>
              <Text style={styles.sched}>
                {s.every_night ? "Every night · tap for shifts only" : `${s.shift_event_ids.length} shift${s.shift_event_ids.length === 1 ? "" : "s"} · tap for every night`}
              </Text>
            </Pressable>
          </View>
          <Pressable testID={`staff-remove-${s.id}`} onPress={() => confirmRemove(s.id, s.name)} style={styles.removeBtn} hitSlop={8}>
            <FeatherIcon name="x" size={16} color={colors.muted} />
          </Pressable>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm, borderWidth: 1, borderColor: colors.border },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "800" },
  sub: { color: colors.muted, fontSize: 13 },
  chips: { flexDirection: "row", flexWrap: "wrap", gap: spacing.sm },
  chip: { paddingHorizontal: spacing.md, height: 44, borderRadius: radius.pill, justifyContent: "center", borderWidth: 1, borderColor: colors.borderStrong, maxWidth: 200 },
  chipOn: { borderColor: colors.brandPrimary, backgroundColor: colors.brandTertiary },
  chipText: { color: colors.muted, fontWeight: "700", fontSize: 13 },
  chipTextOn: { color: colors.brandPrimary },
  inputRow: { flexDirection: "row", gap: spacing.sm },
  input: {
    flex: 1, height: 48, borderRadius: radius.md, paddingHorizontal: spacing.md, color: colors.onSurface,
    backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, fontSize: 15,
  },
  invite: { height: 48, paddingHorizontal: spacing.lg, borderRadius: radius.md, alignItems: "center", justifyContent: "center", backgroundColor: colors.brandPrimary },
  inviteText: { color: colors.onBrandPrimary, fontWeight: "800" },
  row: { flexDirection: "row", alignItems: "center", paddingVertical: spacing.sm, borderTopWidth: 0.5, borderTopColor: colors.divider },
  name: { color: colors.onSurface, fontSize: 15, fontWeight: "700", flexShrink: 1 },
  nameRow: { flexDirection: "row", alignItems: "center", gap: spacing.sm },
  badge: {
    color: colors.brandPrimary, fontSize: 11, fontWeight: "800", paddingHorizontal: spacing.sm, paddingVertical: 2,
    borderRadius: radius.pill, backgroundColor: colors.brandTertiary, overflow: "hidden", flexShrink: 0,
  },
  sched: { color: colors.brandPrimary, fontSize: 12, fontWeight: "700", paddingVertical: 14 },
  removeBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },
  err: { color: colors.error, fontSize: 13 },
});
