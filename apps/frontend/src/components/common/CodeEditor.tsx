import Editor from "@monaco-editor/react";
import { useThemeStore } from "@/stores/theme";

export function CodeEditor({
  value,
  onChange,
  language = "python",
  height = 320,
}: {
  value: string;
  onChange: (v: string) => void;
  language?: string;
  height?: number | string;
}) {
  const theme = useThemeStore((s) => s.resolved);
  return (
    <div className="border border-line-strong rounded-md overflow-hidden">
      <Editor
        height={height}
        theme={theme === "dark" ? "vs-dark" : "light"}
        defaultLanguage={language}
        language={language}
        value={value}
        onChange={(v) => onChange(v ?? "")}
        options={{
          minimap: { enabled: false },
          fontSize: 14,
          lineNumbers: "on",
          scrollBeyondLastLine: false,
          automaticLayout: true,
        }}
      />
    </div>
  );
}
