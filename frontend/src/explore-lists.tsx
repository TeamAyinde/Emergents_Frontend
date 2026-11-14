import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useRouter } from "expo-router";
import { useState } from "react";
import { ActivityIndicator, FlatList, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, Article, Partner, PARTNER_LABELS } from "./api";
import { colors, radius, spacing } from "./theme";
import { LevelBadge } from "./levels";

const CATS = ["all", "hotel", "black_car", "limo", "exotic_car", "mansion", "yacht", "jet", "helicopter", "chef", "security"];

export function LuxeList() {
  const router = useRouter();
  const [cat, setCat] = useState("all");
  const { data, isLoading } = useQuery({
    queryKey: ["partners", cat],
    queryFn: () => api.listPartners(cat === "all" ? undefined : cat),
  });

  return (
    <View style={{ flex: 1 }}>
      <View style={styles.chipWrap}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRow}>
          {CATS.map((c) => (
            <Pressable
              key={c}
              testID={`luxe-chip-${c}`}
              onPress={() => setCat(c)}
              style={[styles.chip, cat === c && styles.chipOn]}
            >
              <Text style={[styles.chipText, cat === c && styles.chipTextOn]}>
                {c === "all" ? "All" : PARTNER_LABELS[c] ?? c}
              </Text>
            </Pressable>
          ))}
        </ScrollView>
      </View>
      {isLoading ? (
        <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />
      ) : (
        <FlatList
          data={data ?? []}
          keyExtractor={(p) => p.id}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["2xl"], gap: spacing.md }}
          renderItem={({ item }) => <PartnerCard p={item} onPress={() => router.push(`/partner/${item.id}`)} />}
          ListEmptyComponent={<Text style={styles.empty}>No partners in this category yet.</Text>}
        />
      )}
    </View>
  );
}

function PartnerCard({ p, onPress }: { p: Partner; onPress: () => void }) {
  return (
    <Pressable testID={`partner-${p.id}`} onPress={onPress} style={styles.pCard}>
      <Image source={p.image_url} style={StyleSheet.absoluteFill} contentFit="cover" />
      <LinearGradient
        colors={["transparent", "rgba(9,9,11,0.95)"]}
        locations={[0.3, 1]}
        style={StyleSheet.absoluteFill}
      />
      <View style={styles.pBadge}>
        <Text style={styles.pBadgeText}>{(PARTNER_LABELS[p.category] ?? p.category).toUpperCase()}</Text>
      </View>
      <LevelBadge level={p.min_level} floating />
      <View style={styles.pBottom}>
        <Text style={styles.pName} numberOfLines={1}>{p.name}</Text>
        <View style={styles.pMeta}>
          <Text style={styles.pCity}>{p.city} · ★ {p.rating.toFixed(1)}</Text>
          <Text style={styles.pPrice}>members ${p.base_price}/{p.price_unit}</Text>
        </View>
      </View>
    </Pressable>
  );
}

export function JournalList() {
  const router = useRouter();
  const { data, isLoading } = useQuery({ queryKey: ["journal"], queryFn: () => api.listArticles() });
  if (isLoading) return <ActivityIndicator color={colors.brandPrimary} style={{ marginTop: spacing["2xl"] }} />;
  return (
    <FlatList
      data={data ?? []}
      keyExtractor={(a) => a.id}
      contentContainerStyle={{ padding: spacing.lg, paddingBottom: spacing["2xl"], gap: spacing.lg }}
      renderItem={({ item }) => <ArticleCard a={item} onPress={() => router.push(`/journal/${item.id}`)} />}
      ListEmptyComponent={<Text style={styles.empty}>The first issue drops soon.</Text>}
    />
  );
}

function ArticleCard({ a, onPress }: { a: Article; onPress: () => void }) {
  return (
    <Pressable testID={`article-${a.id}`} onPress={onPress} style={styles.aCard}>
      <Image source={a.cover_image} style={styles.aImg} contentFit="cover" />
      <View style={styles.aBody}>
        <Text style={styles.aCat}>{a.category.toUpperCase()}</Text>
        <Text style={styles.aTitle} numberOfLines={2}>{a.title}</Text>
        {a.summary ? <Text style={styles.aSummary} numberOfLines={2}>{a.summary}</Text> : null}
        <View style={styles.aRead}>
          <Text style={styles.aReadText}>Read</Text>
          <FeatherIcon name="arrow-right" size={14} color={colors.brandPrimary} />
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  chipWrap: { height: 56, justifyContent: "center" },
  chipRow: { paddingHorizontal: spacing.lg, gap: spacing.sm, alignItems: "center" },
  chip: {
    flexShrink: 0, height: 40, paddingHorizontal: spacing.lg, borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  chipOn: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurfaceSecondary, fontSize: 13, fontWeight: "600" },
  chipTextOn: { color: colors.onBrandPrimary },
  empty: { color: colors.muted, textAlign: "center", paddingTop: spacing["2xl"] },
  pCard: {
    height: 200, borderRadius: radius.lg, overflow: "hidden",
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
  },
  pBadge: {
    position: "absolute", top: spacing.md, left: spacing.md, backgroundColor: colors.brandSecondary,
    paddingHorizontal: spacing.sm, paddingVertical: 4, borderRadius: radius.sm,
  },
  pBadgeText: { color: colors.onBrandSecondary, fontSize: 10, fontWeight: "800", letterSpacing: 1 },
  pBottom: { position: "absolute", left: spacing.lg, right: spacing.lg, bottom: spacing.lg },
  pName: { color: colors.onSurface, fontSize: 20, fontWeight: "800" },
  pMeta: { flexDirection: "row", justifyContent: "space-between", marginTop: 4 },
  pCity: { color: colors.muted, fontSize: 12 },
  pPrice: { color: colors.brandPrimary, fontSize: 13, fontWeight: "700" },
  aCard: {
    borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
  },
  aImg: { width: "100%", height: 170 },
  aBody: { padding: spacing.lg, gap: 6 },
  aCat: { color: colors.brandPrimary, fontSize: 10, letterSpacing: 2, fontWeight: "800" },
  aTitle: { color: colors.onSurface, fontSize: 19, fontWeight: "800" },
  aSummary: { color: colors.muted, fontSize: 13, lineHeight: 19 },
  aRead: { flexDirection: "row", alignItems: "center", gap: 4, marginTop: 4 },
  aReadText: { color: colors.brandPrimary, fontSize: 13, fontWeight: "700" },
});
