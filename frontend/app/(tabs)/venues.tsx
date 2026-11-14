import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, Venue } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

export default function Venues() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [q, setQ] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["venues", q],
    queryFn: () => api.listVenues(q || undefined),
  });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.title}>Venues</Text>
        <Text style={styles.subtitle}>{"California's best clubs, lounges & restaurants."}</Text>
        <View style={styles.search}>
          <FeatherIcon name="search" color={colors.muted} size={16} />
          <TextInput
            testID="venue-search"
            placeholder="Search venues"
            placeholderTextColor={colors.muted}
            value={q}
            onChangeText={setQ}
            style={styles.searchInput}
          />
        </View>
      </View>

      {isLoading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(v) => v.id}
          numColumns={2}
          columnWrapperStyle={{ gap: spacing.md }}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing["3xl"], gap: spacing.md }}
          renderItem={({ item }) => <VenueCard v={item} onPress={() => router.push(`/venue/${item.id}`)} />}
        />
      )}
    </View>
  );
}

function VenueCard({ v, onPress }: { v: Venue; onPress: () => void }) {
  return (
    <Pressable testID={`venue-${v.id}`} onPress={onPress} style={styles.card}>
      <Image source={v.image_url} style={styles.cardImg} contentFit="cover" />
      <View style={styles.cardBody}>
        <View style={styles.rowBetween}>
          <Text style={styles.cat}>{v.category.toUpperCase()}</Text>
          <View style={styles.rating}>
            <FeatherIcon name="star" size={10} color={colors.brandPrimary} />
            <Text style={styles.ratingText}>{v.rating.toFixed(1)}</Text>
          </View>
        </View>
        <Text style={styles.name} numberOfLines={1}>{v.name}</Text>
        <Text style={styles.city}>{v.city} · {v.price_range}</Text>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: { paddingHorizontal: spacing.lg, paddingBottom: spacing.md, gap: spacing.sm },
  title: { color: colors.onSurface, fontSize: 32, fontWeight: "800" },
  subtitle: { color: colors.muted, fontSize: 13 },
  search: {
    flexDirection: "row", alignItems: "center", gap: spacing.sm,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.pill,
    paddingHorizontal: spacing.lg, borderWidth: 1, borderColor: colors.border, marginTop: spacing.sm,
  },
  searchInput: { flex: 1, color: colors.onSurface, fontSize: 15, paddingVertical: 12 },
  card: {
    flex: 1, borderRadius: radius.lg, overflow: "hidden",
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },
  cardImg: { width: "100%", height: 130 },
  cardBody: { padding: spacing.md, gap: 4 },
  cat: { color: colors.brandPrimary, fontSize: 9, letterSpacing: 1.5, fontWeight: "700" },
  rating: { flexDirection: "row", alignItems: "center", gap: 2 },
  ratingText: { color: colors.onSurface, fontSize: 11, fontWeight: "700" },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  name: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  city: { color: colors.muted, fontSize: 12 },
});
