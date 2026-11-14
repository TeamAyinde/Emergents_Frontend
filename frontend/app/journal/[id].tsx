import { useQuery } from "@tanstack/react-query";
import { Image } from "expo-image";
import { LinearGradient } from "expo-linear-gradient";
import { useLocalSearchParams, useRouter } from "expo-router";
import { ActivityIndicator, Pressable, ScrollView, Share, StyleSheet, Text, View } from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { colors, radius, spacing } from "@/src/theme";

export default function ArticleScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { data: a, isLoading } = useQuery({ queryKey: ["article", id], queryFn: () => api.getArticle(id!) });

  if (isLoading || !a) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={colors.brandPrimary} />
      </View>
    );
  }

  return (
    <View style={styles.root}>
      <ScrollView contentContainerStyle={{ paddingBottom: insets.bottom + spacing["2xl"] }}>
        <View style={styles.hero}>
          <Image source={a.cover_image} style={StyleSheet.absoluteFill} contentFit="cover" />
          <LinearGradient colors={["rgba(9,9,11,0.5)", "transparent", "rgba(9,9,11,1)"]} locations={[0, 0.4, 1]} style={StyleSheet.absoluteFill} />
          <View style={[styles.topBar, { top: insets.top + spacing.sm }]}>
            <Pressable testID="article-back" onPress={() => router.back()} style={styles.iconBtn}>
              <FeatherIcon name="chevron-left" size={22} color={colors.onSurface} />
            </Pressable>
            <Pressable
              testID="article-share"
              onPress={() => Share.share({ message: `${a.title} — read it on Nocturne Journal` }).catch(() => {})}
              style={styles.iconBtn}
            >
              <FeatherIcon name="share-2" size={18} color={colors.onSurface} />
            </Pressable>
          </View>
        </View>
        <View style={styles.body}>
          <Text style={styles.cat}>NOCTURNE JOURNAL · {a.category.toUpperCase()}</Text>
          <Text style={styles.title} testID="article-title">{a.title}</Text>
          {a.summary ? <Text style={styles.summary}>{a.summary}</Text> : null}
          <Text style={styles.date}>{new Date(a.created_at).toLocaleDateString("en", { month: "long", day: "numeric", year: "numeric" })}</Text>
          <View style={styles.rule} />
          {a.body.split(/\n+/).filter(Boolean).map((para, i) => (
            <Text key={i} style={styles.para}>{para}</Text>
          ))}
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.surface },
  center: { alignItems: "center", justifyContent: "center" },
  hero: { height: 320 },
  topBar: { position: "absolute", left: spacing.lg, right: spacing.lg, flexDirection: "row", justifyContent: "space-between" },
  iconBtn: {
    width: 40, height: 40, borderRadius: 20, backgroundColor: "rgba(9,9,11,0.5)",
    alignItems: "center", justifyContent: "center", borderWidth: 1, borderColor: colors.border,
  },
  body: { paddingHorizontal: spacing.xl, gap: spacing.md, marginTop: -spacing.xl },
  cat: { color: colors.brandPrimary, fontSize: 11, letterSpacing: 2, fontWeight: "800" },
  title: { color: colors.onSurface, fontSize: 30, fontWeight: "800", lineHeight: 36 },
  summary: { color: colors.onSurfaceSecondary, fontSize: 16, lineHeight: 24, fontStyle: "italic" },
  date: { color: colors.muted, fontSize: 12 },
  rule: { height: 1, backgroundColor: colors.brandPrimary, width: 48, marginVertical: spacing.sm, borderRadius: radius.pill },
  para: { color: colors.onSurfaceSecondary, fontSize: 16, lineHeight: 26 },
});
