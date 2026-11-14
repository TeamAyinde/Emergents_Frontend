// Nocturne — Luxe Dark nightlife theme. Dark-only.
import { useMemo } from "react";
import { Appearance, StyleSheet, useColorScheme } from "react-native";

export type ColorScheme = "light" | "dark";

const dark = {
  // Surfaces
  surface: "#09090B",
  onSurface: "#FAFAFA",
  surfaceSecondary: "#18181B",
  onSurfaceSecondary: "#E4E4E7",
  surfaceTertiary: "#27272A",
  onSurfaceTertiary: "#D4D4D8",
  surfaceInverse: "#FFFFFF",
  onSurfaceInverse: "#000000",
  muted: "#A1A1AA",

  // Brand (amber/gold)
  brand: "#F5B041",
  onBrand: "#452800",
  brandPrimary: "#E5A93C",
  onBrandPrimary: "#452800",
  // Secondary (crimson red)
  brandSecondary: "#DC2626",
  onBrandSecondary: "#FFFFFF",
  // Tertiary (dark gold tint for stat cards)
  brandTertiary: "#451A03",
  onBrandTertiary: "#FDE68A",

  // Status
  success: "#10B981",
  onSuccess: "#022C22",
  warning: "#F59E0B",
  onWarning: "#451A03",
  error: "#EF4444",
  onError: "#450A0A",
  info: "#3B82F6",
  onInfo: "#FAFAFA",

  // Lines
  border: "#27272A",
  borderStrong: "#3F3F46",
  divider: "#27272A",
};

export type ThemeColors = typeof dark;

export const defaultScheme = "dark" satisfies ColorScheme;

export const themes: { light?: ThemeColors; dark: ThemeColors } = { dark };

export function setColorScheme(scheme: ColorScheme | null) {
  Appearance.setColorScheme?.(scheme ?? "unspecified");
}

// Force dark across native chrome.
setColorScheme?.(defaultScheme);

export function useTheme(): { scheme: ColorScheme; colors: ThemeColors } {
  const system = useColorScheme();
  // Always dark for this app.
  return { scheme: "dark", colors: themes.dark };
}

export const colors = dark;

export const spacing = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  "2xl": 32,
  "3xl": 48,
} as const;

export const radius = {
  sm: 6,
  md: 12,
  lg: 20,
  pill: 999,
} as const;

export const typography = {
  display: "Fraunces_600SemiBold",
  displayBold: "Fraunces_700Bold",
  text: "Geist_400Regular",
  textMedium: "Geist_500Medium",
  textBold: "Geist_700Bold",
} as const;

export function makeStyles<T extends StyleSheet.NamedStyles<T> | StyleSheet.NamedStyles<any>>(
  factory: (colors: ThemeColors) => T & StyleSheet.NamedStyles<any>,
): () => T {
  return function useStyles(): T {
    const { colors } = useTheme();
    return useMemo(() => StyleSheet.create(factory(colors)), [colors]);
  };
}
