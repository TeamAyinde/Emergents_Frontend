import { File, Paths } from "expo-file-system";
import * as Sharing from "expo-sharing";
import { Platform } from "react-native";

/** Saves a CSV: browser download on web, native share sheet (Files, Mail, Drive…) on phones. */
export async function saveCsv(csv: string, filename: string) {
  if (Platform.OS === "web") {
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
    return;
  }
  const file = new File(Paths.cache, filename);
  file.create({ overwrite: true });
  file.write(csv);
  if (!(await Sharing.isAvailableAsync())) throw new Error("Sharing isn't available on this device");
  await Sharing.shareAsync(file.uri, { mimeType: "text/csv", UTI: "public.comma-separated-values-text", dialogTitle: filename });
}
