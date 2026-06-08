#!/usr/bin/env bash
# Reproducible build of the patched MAPA COBOL "CallTree" jar.
#
# Vendoring approach (b): we keep PRISTINE upstream MAPA source under upstream/,
# our delta as the standalone reviewable patch mapa_origin_tracker.patch, and this
# documented build step. The patch is applied to a throwaway build/ copy so
# upstream/ stays pristine and our diff stays reviewable against it.
#
# Output: ./CallTree.jar  (the COBOL adapter's Parse seam invokes this)
#
# Requirements: a JDK (tested with JDK 22; MAPA targets 17+) on PATH.
set -euo pipefail
cd "$(dirname "$0")"

JAVAC="${JAVAC:-javac}"
JAVA="${JAVA:-java}"
ANTLR="upstream/antlr-4.13.2-complete.jar"
CP="upstream/antlr-4.13.2-complete.jar:upstream/CICSz.jar:upstream/DLI.jar:upstream/DB2zSQL.jar:upstream/commons-cli-1.4.jar"

echo ">> staging pristine upstream -> build/"
rm -rf build && cp -r upstream build

echo ">> applying mapa_origin_tracker.patch (our standalone delta)"
# patch paths are a/cobol/src/... ; build/ mirrors cobol/, so strip 2 components.
patch -p2 -d build < mapa_origin_tracker.patch

echo ">> generating ANTLR parser sources (lexer before parser)"
cd build
"$JAVA" -jar "../$ANTLR" -visitor -listener src/CobolLexer.g4
"$JAVA" -jar "../$ANTLR" -visitor -listener src/CobolParser.g4
"$JAVA" -jar "../$ANTLR" -visitor -listener src/CobolPreprocessorLexer.g4
"$JAVA" -jar "../$ANTLR" -visitor -listener src/CobolPreprocessorParser.g4

echo ">> compiling (single-shot; per-file make chokes on mutual class refs)"
rm -rf class && mkdir -p class
"$JAVAC" -d class -cp "class:../$ANTLR:../upstream/CICSz.jar:../upstream/DLI.jar:../upstream/DB2zSQL.jar:../upstream/commons-cli-1.4.jar" \
  -sourcepath src src/*.java

echo ">> packaging CallTree.jar"
# The output jar lives one level up from the build-dep jars (jar in vendor/mapa/,
# deps in vendor/mapa/upstream/), so rewrite the manifest Class-Path to resolve
# deps under upstream/ relative to the jar. Keeps `java -jar CallTree.jar` working
# without copying the ~11MB of jars or touching pristine upstream/manifest.
{
  echo "Main-Class: TestIntegration"
  printf "Class-Path:"
  for j in commons-cli-1.4.jar antlr-4.13.2-complete.jar DB2zSQL.jar CICSz.jar DLI.jar; do
    printf " upstream/%s" "$j"
  done
  echo
} > manifest.packaged
jar cfm CallTree.jar manifest.packaged -C class .
cd ..
cp build/CallTree.jar CallTree.jar

echo ">> compiling MapaTreeDump (our data-layer tree dumper) against CallTree.jar"
"$JAVAC" -cp "CallTree.jar:upstream/antlr-4.13.2-complete.jar" -d . MapaTreeDump.java

echo ">> done: $(pwd)/CallTree.jar + MapaTreeDump.class"
ls -lh CallTree.jar MapaTreeDump.class
