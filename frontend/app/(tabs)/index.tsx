import { useQuery } from "@tanstack/react-query";
import { LinearGradient } from "expo-linear-gradient";
import { Image } from "expo-image";
import { useRouter } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api, EventItem } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { colors, radius, spacing } from "@/src/theme";
import { LevelBadge } from "@/src/levels";

const CATEGORIES = ["All", "Tonight", "This Week", "VIP", "DJ", "Open Bar"];

function matches(e: EventItem, c: string) {
  const hours = (new Date(e.date).getTime() - Date.now()) / 3600000;
  if (c === "Tonight") return hours <= 24;
  if (c === "This Week") return hours <= 24 * 7;
  if (c === "All") return true;
  return e.tags.includes(c);
}

export default function Home() {
  const insets = useSafeAreaInsets();
  const router = useRouter();
  const { user } = useAuth();
  const isStaff = user?.role === "promoter" || user?.role === "venue_owner" || user?.role === "admin";
  const [category, setCategory] = useState("All");
  const { data: events, isLoading, refetch, isRefetching } = useQuery({
    queryKey: ["events"],
    queryFn: () => api.listEvents(),
  });
  const filtered = (events ?? []).filter((e) => matches(e, category));
  const { data: unread } = useQuery({ queryKey: ["concierge-unread"], queryFn: () => api.conciergeUnread(), refetchInterval: 15000 });

  return (
    <View style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <View>
          <Text style={styles.hello} testID="home-hello">Good evening,</Text>
          <Text style={styles.name} testID="home-name">{user?.full_name?.split(" ")[0] ?? "friend"}</Text>
        </View>
        <View style={{ flexDirection: "row", gap: spacing.sm }}>
          <Pressable testID="home-concierge-btn" onPress={() => router.push("/concierge")} style={styles.scanBtn}>
            <FeatherIcon name="message-circle" color={colors.brandPrimary} size={20} />
            {unread?.unread ? <View style={styles.unreadDot} testID="concierge-unread-dot" /> : null}
          </Pressable>
          {user?.role === "venue_owner" || user?.role === "admin" ? (
            <Pressable testID="home-host-btn" onPress={() => router.push("/host/new-event")} style={styles.scanBtn}>
              <FeatherIcon name="plus" color={colors.brandPrimary} size={20} />
            </Pressable>
          ) : null}
        {isStaff ? (
          <Pressable
            testID="scan-btn"
            onPress={() => router.push("/checkin")}
            style={styles.scanBtn}
          >
            <FeatherIcon name="maximize" color={colors.brandPrimary} size={20} />
          </Pressable>
        ) : null}
        </View>
      </View>

      <View style={styles.chipScroll}>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.chipRow}
      >
        {CATEGORIES.map((c) => {
          const selected = c === category;
          return (
            <Pressable
              key={c}
              testID={`chip-${c}`}
              onPress={() => setCategory(c)}
              style={[styles.chip, selected && styles.chipSelected]}
            >
              <Text style={[styles.chipText, selected && styles.chipTextSelected]}>{c}</Text>
            </Pressable>
          );
        })}
      </ScrollView>
      </View>

      {isLoading ? (
        <View style={styles.loading}>
          <ActivityIndicator color={colors.brandPrimary} size="large" />
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={(i) => i.id}
          renderItem={({ item }) => <EventCard item={item} onPress={() => router.push(`/event/${item.id}`)} />}
          contentContainerStyle={{ padding: spacing.lg, paddingBottom: insets.bottom + spacing["3xl"], gap: spacing.lg }}
          refreshControl={<RefreshControl refreshing={isRefetching} onRefresh={refetch} tintColor={colors.brandPrimary} />}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text style={styles.emptyTitle}>No events match</Text>
              <Text style={styles.emptyText}>Try another filter or pull to refresh.</Text>
            </View>
          }
        />
      )}
    </View>
  );
}

function EventCard({ item, onPress }: { item: EventItem; onPress: () => void }) {
  const d = new Date(item.date);
  return (
    <Pressable testID={`event-card-${item.id}`} onPress={onPress} style={styles.card}>
      <Image source={item.image_url} style={styles.cardImg} contentFit="cover" />
      <LinearGradient
        colors={["transparent", "rgba(9,9,11,0.3)", "rgba(9,9,11,0.95)"]}
        locations={[0, 0.4, 1]}
        style={StyleSheet.absoluteFill}
      />
      <View style={styles.cardTop}>
        <View style={styles.dateBadge}>
          <Text style={styles.dateDay}>{d.getDate()}</Text>
          <Text style={styles.dateMonth}>{d.toLocaleString("en", { month: "short" }).toUpperCase()}</Text>
        </View>
        <View style={{ alignItems: "flex-end", gap: 6 }}>
          <View style={styles.cityBadge}>
            <FeatherIcon name="map-pin" color={colors.onSurface} size={10} />
            <Text style={styles.cityText}>{item.city}</Text>
          </View>
          <LevelBadge level={item.min_level} />
        </View>
      </View>
      <View style={styles.cardBottom}>
        <View style={{ flexDirection: "row", gap: spacing.xs, marginBottom: spacing.xs }}>
          {item.tags.slice(0, 2).map((t) => (
            <View key={t} style={styles.tag}>
              <Text style={styles.tagText}>{t}</Text>
            </View>
          ))}
        </View>
        <Text style={styles.cardTitle} numberOfLines={2}>{item.title}</Text>
        <View style={styles.cardMeta}>
          <Text style={styles.cardVenue}>{item.venue_name}</Text>
          <Text style={styles.cardPrice}>${item.price.toFixed(0)}</Text>
        </View>
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  hello: { color: colors.muted, fontSize: 13 },
  name: { color: colors.onSurface, fontSize: 24, fontWeight: "800", marginTop: 2 },
  scanBtn: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  chipScroll: { height: 56, justifyContent: "center" },
  unreadDot: { position: "absolute", top: 8, right: 8, width: 10, height: 10, borderRadius: 5, backgroundColor: colors.brandSecondary },
  chipRow: { paddingHorizontal: spacing.lg, gap: spacing.sm, alignItems: "center" },
  chip: {
    flexShrink: 0, height: 40, paddingHorizontal: spacing.lg,
    borderRadius: radius.pill,
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border,
    alignItems: "center", justifyContent: "center",
  },
  chipSelected: { backgroundColor: colors.brandPrimary, borderColor: colors.brandPrimary },
  chipText: { color: colors.onSurfaceSecondary, fontSize: 13, fontWeight: "600" },
  chipTextSelected: { color: colors.onBrandPrimary },
  loading: { flex: 1, alignItems: "center", justifyContent: "center" },
  empty: { alignItems: "center", paddingTop: spacing["3xl"] },
  emptyTitle: { color: colors.onSurface, fontSize: 18, fontWeight: "700" },
  emptyText: { color: colors.muted, marginTop: spacing.sm },
  card: {
    height: 240,
    borderRadius: radius.lg,
    overflow: "hidden",
    backgroundColor: colors.surfaceSecondary,
    borderWidth: 1,
    borderColor: colors.border,
  },
  cardImg: { ...StyleSheet.absoluteFillObject },
  cardTop: {
    position: "absolute", top: spacing.md, left: spacing.md, right: spacing.md,
    flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start",
  },
  dateBadge: {
    backgroundColor: "rgba(9,9,11,0.7)", borderRadius: radius.md,
    paddingHorizontal: spacing.sm, paddingVertical: 6, alignItems: "center",
    borderWidth: 1, borderColor: colors.brandPrimary,
  },
  dateDay: { color: colors.brandPrimary, fontWeight: "800", fontSize: 18, lineHeight: 20 },
  dateMonth: { color: colors.brandPrimary, fontSize: 10, letterSpacing: 1, fontWeight: "700" },
  cityBadge: {
    flexDirection: "row", alignItems: "center", gap: 4,
    backgroundColor: "rgba(9,9,11,0.6)", paddingHorizontal: spacing.sm, paddingVertical: 4,
    borderRadius: radius.pill,
  },
  cityText: { color: colors.onSurface, fontSize: 11, fontWeight: "600" },
  cardBottom: { position: "absolute", bottom: spacing.lg, left: spacing.lg, right: spacing.lg },
  tag: {
    backgroundColor: "rgba(220,38,38,0.85)", paddingHorizontal: spacing.sm, paddingVertical: 3,
    borderRadius: radius.sm,
  },
  tagText: { color: colors.onBrandSecondary, fontSize: 10, fontWeight: "700", letterSpacing: 0.5 },
  cardTitle: { color: colors.onSurface, fontSize: 22, fontWeight: "800" },
  cardMeta: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", marginTop: spacing.xs },
  cardVenue: { color: colors.muted, fontSize: 13 },
  cardPrice: { color: colors.brandPrimary, fontSize: 18, fontWeight: "800" },
});
