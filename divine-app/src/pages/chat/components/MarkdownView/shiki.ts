import { createHighlighterCore, type HighlighterCore } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import githubDark from "@shikijs/themes/github-dark";
import githubLight from "@shikijs/themes/github-light";

import javascript from "@shikijs/langs/javascript";
import typescript from "@shikijs/langs/typescript";
import jsx from "@shikijs/langs/jsx";
import tsx from "@shikijs/langs/tsx";
import json from "@shikijs/langs/json";
import markdown from "@shikijs/langs/markdown";
import python from "@shikijs/langs/python";
import bash from "@shikijs/langs/bash";
import yaml from "@shikijs/langs/yaml";
import sql from "@shikijs/langs/sql";
import html from "@shikijs/langs/html";
import xml from "@shikijs/langs/xml";
import css from "@shikijs/langs/css";
import scss from "@shikijs/langs/scss";
import less from "@shikijs/langs/less";
import go from "@shikijs/langs/go";
import rust from "@shikijs/langs/rust";
import java from "@shikijs/langs/java";
import kotlin from "@shikijs/langs/kotlin";
import c from "@shikijs/langs/c";
import cpp from "@shikijs/langs/cpp";
import csharp from "@shikijs/langs/csharp";
import ruby from "@shikijs/langs/ruby";
import php from "@shikijs/langs/php";
import swift from "@shikijs/langs/swift";
import lua from "@shikijs/langs/lua";
import r from "@shikijs/langs/r";
import dockerfile from "@shikijs/langs/dockerfile";
import diff from "@shikijs/langs/diff";
import graphql from "@shikijs/langs/graphql";
import ini from "@shikijs/langs/ini";
import makefile from "@shikijs/langs/makefile";
import vue from "@shikijs/langs/vue";
import svelte from "@shikijs/langs/svelte";
import toml from "@shikijs/langs/toml";

export function highlightTheme(theme: "dark" | "light"): string {
  return theme === "light" ? "github-light" : "github-dark";
}

const LANGS = [
  javascript,
  typescript,
  jsx,
  tsx,
  json,
  markdown,
  python,
  bash,
  yaml,
  sql,
  html,
  xml,
  css,
  scss,
  less,
  go,
  rust,
  java,
  kotlin,
  c,
  cpp,
  csharp,
  ruby,
  php,
  swift,
  lua,
  r,
  dockerfile,
  diff,
  graphql,
  ini,
  makefile,
  vue,
  svelte,
  toml,
];

let highlighterPromise: Promise<HighlighterCore> | null = null;

export function getHighlighter(): Promise<HighlighterCore> {
  highlighterPromise ??= createHighlighterCore({
    themes: [githubDark, githubLight],
    langs: LANGS,
    engine: createJavaScriptRegexEngine(),
  });
  return highlighterPromise;
}
