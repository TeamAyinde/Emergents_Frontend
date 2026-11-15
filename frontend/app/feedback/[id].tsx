import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useLocalSearchParams, useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

/** Opened from the morning-after email: rate the night, earn bonus points. */
export default function Feedback() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const qc = useQueryClient();
  const [rating, setRating] = useState(0);
  const [comment, setComment] = useState("");
  const { data, isLoading, error } = useQuery({ queryKey: ["feedback", id], queryFn: () => api.feedbackInfo(id!), enabled: !!id, retry: false });
  const submit = useMutation({
    mutationFn: () => api.submitFeedback(id!, rating, comment.trim() || undefined),
    onSuccess: () => qc.invalidateQueries(),
  });
  const done = submit.isSuccess || data?.submitted;

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="feedback-back" onPress={() => (router.canGoBack() ? router.back() : router.replace("/(tabs)"))} style={styles.iconBtn}>
          <FeatherIcon name="x" size={20} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.headerTitle}>Rate your night</Text>
        <View style={{ width: 44 }} />
      </View>
      {isLoading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : error || !data ? (
        <Text style={[styles.sub, { padding: spacing.lg }]} testID="feedback-error">{error?.message ?? "Ticket not found"}</Text>
      ) : (
        <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: spacing.lg, gap: spacing.lg, paddingBottom: insets.bottom + spacing["2xl"] }}>
          <View>
            <Text style={styles.title}>{data.event_title}</Text>
            <Text style={styles.sub}>{data.venue_name}</Text>
          </View>
          {!done && !data.can_rate ? (
            <Text style={styles.sub} testID="feedback-too-early">Come back after the night to rate it and earn {data.points} points.</Text>
          ) : done ? (
            <View style={styles.doneBox} testID="feedback-done">
              <FeatherIcon name="check-circle" size={28} color={colors.success} />
              <Text style={styles.doneText}>
                {submit.isSuccess ? `Thank you! ${submit.data.points} bonus points added.` : "You've already rated this night — thank you!"}
              </Text>
              <LuxButton testID="feedback-rewards-btn" label="See my rewards" variant="secondary" onPress={() => router.replace("/rewards")} />
            </View>
          ) : (
            <>
              <View style={styles.stars}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <Pressable
                    key={n}
                    testID={`star-${n}`}
                    onPress={() => setRating(n)}
                    style={[styles.star, n <= rating && styles.starOn]}
                    hitSlop={6}
                  >
                    <FeatherIcon name="star" size={30} color={n <= rating ? colors.onBrandPrimary : colors.muted} />
                  </Pressable>
                ))}
              </View>
              <TextInput
                testID="feedback-comment"
                value={comment}
                onChangeText={setComment}
                placeholder="Anything we should know? (optional)"
                placeholderTextColor={colors.muted}
                multiline
                maxLength={500}
                style={styles.input}
              />
              {submit.error ? <Text style={styles.err}>{submit.error.message}</Text> : null}
              <LuxButton
                testID="feedback-submit"
                label={rating ? `Submit · earn ${data.points} points` : "Tap a star to rate"}
                onPress={() => submit.mutate()}
                disabled={!rating}
                loading={submit.isPending}
              />
            </>
          )}
        </ScrollView>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  headerTitle: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  iconBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  title: { color: colors.onSurface, fontSize: 24, fontWeight: "800" },
  sub: { color: colors.muted, fontSize: 14, marginTop: 4 },
  stars: { flexDirection: "row", justifyContent: "center", gap: spacing.sm },
  star: { width: 52, height: 52, borderRadius: 26, borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center" },
  starOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  input: {
    minHeight: 100, borderRadius: radius.md, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surfaceSecondary,
    color: colors.onSurface, padding: spacing.md, fontSize: 15, textAlignVertical: "top",
  },
  err: { color: colors.error, fontSize: 13 },
  doneBox: { alignItems: "center", gap: spacing.md, padding: spacing.xl, backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg },
  doneText: { color: colors.onSurface, fontSize: 16, fontWeight: "700", textAlign: "center" },
});
