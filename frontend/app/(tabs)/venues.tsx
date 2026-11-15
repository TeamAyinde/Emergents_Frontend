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
import { LuxeList, JournalList } from "@/src/explore-lists";
import { LevelBadge } from "@/src/levels";
import { FeaturedBadge } from "@/src/featured-badge";

export default function Venues() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<"venues" | "luxe" | "journal">("venues");
  const { data, isLoading } = useQuery({
    queryKey: ["venues", q],
    queryFn: () => api.listVenues(q || undefined),
  });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Text style={styles.title}>Explore</Text>
        <View style={styles.segment}>
          {(["venues", "luxe", "journal"] as const).map((t) => (
            <Pressable
              key={t}
              testID={`explore-tab-${t}`}
              onPress={() => setTab(t)}
              style={[styles.segBtn, tab === t && styles.segBtnOn]}
            >
              <Text style={[styles.segText, tab === t && styles.segTextOn]}>
                {t === "venues" ? "Venues" : t === "luxe" ? "Luxe Services" : "Journal"}
              </Text>
            </Pressable>
          ))}
        </View>
        {tab === "venues" ? (
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
        ) : null}
      </View>

      {tab === "luxe" ? (
        <LuxeList />
      ) : tab === "journal" ? (
        <JournalList />
      ) : isLoading ? (
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
      <LevelBadge level={v.min_level} floating />
      {v.featured ? (
        <View style={styles.featuredFloat}>
          <FeaturedBadge testID={`venue-featured-${v.id}`} />
        </View>
      ) : null}
      <View style={styles.cardBody}>
        <View style={styles.rowBetween}>
          <Text style={styles.cat}>{v.category.toUpperCase()}</Text>
          <View style={styles.rating} testID={`venue-rating-${v.id}`}>
            <FeatherIcon name="star" size={10} color={colors.brandPrimary} />
            <Text style={styles.ratingText}>
              {(v.guest_rating ?? v.rating).toFixed(1)}
              {v.guest_rating_count ? ` (${v.guest_rating_count})` : ""}
            </Text>
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
  segment: {
    flexDirection: "row", backgroundColor: colors.surfaceSecondary, borderRadius: radius.pill,
    padding: 4, borderWidth: 1, borderColor: colors.border,
  },
  segBtn: { flex: 1, height: 40, borderRadius: radius.pill, alignItems: "center", justifyContent: "center" },
  segBtnOn: { backgroundColor: colors.brandPrimary },
  segText: { color: colors.onSurfaceSecondary, fontSize: 13, fontWeight: "700" },
  segTextOn: { color: colors.onBrandPrimary },
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
  featuredFloat: { position: "absolute", top: spacing.sm, left: spacing.sm },
  cardBody: { padding: spacing.md, gap: 4 },
  cat: { color: colors.brandPrimary, fontSize: 9, letterSpacing: 1.5, fontWeight: "700" },
  rating: { flexDirection: "row", alignItems: "center", gap: 2 },
  ratingText: { color: colors.onSurface, fontSize: 11, fontWeight: "700" },
  rowBetween: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  name: { color: colors.onSurface, fontSize: 15, fontWeight: "700" },
  city: { color: colors.muted, fontSize: 12 },
});
