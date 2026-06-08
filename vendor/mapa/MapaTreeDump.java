// MapaTreeDump — part of carddemo-graph's MAPA integration (the Parse seam's
// data-layer tree dumper). NOT upstream MAPA: this is our glue, compiled against
// MAPA's generated CobolLexer/CobolParser (bundled in CallTree.jar). MIT-compatible.
//
// Feeds an already-preprocessed (cols<=72, copy-expanded) COBOL source to MAPA's
// CobolParser and dumps the ANTLR parse tree as nested JSON
//   {"r": ruleName, "ln": startLine, "le": stopLine, "k": [children...]}
// with terminals as bare JSON strings. The COBOL data layer (DataItem hierarchy,
// PIC/USAGE/OCCURS/REDEFINES) is recovered by the Python Map seam walking this tree.
// Syntax-error count is written to stderr as SYNTAX_ERRORS=<n>.
import org.antlr.v4.runtime.*;
import org.antlr.v4.runtime.tree.*;

public class MapaTreeDump {
    public static void main(String[] args) throws Exception {
        CobolLexer.testRig = false;
        CobolLexer.nistTest = false;
        CobolLexer.freeForm = false;
        CharStream cs = CharStreams.fromFileName(args[0]);
        CobolLexer lexer = new CobolLexer(cs);
        CommonTokenStream tokens = new CommonTokenStream(lexer);
        CobolParser parser = new CobolParser(tokens);
        parser.removeErrorListeners();
        final int[] errs = {0};
        parser.addErrorListener(new BaseErrorListener() {
            public void syntaxError(Recognizer<?,?> r, Object o, int line, int col, String msg, RecognitionException e) { errs[0]++; }
        });
        ParserRuleContext tree = parser.startRule();
        StringBuilder sb = new StringBuilder();
        dump(tree, parser, sb);
        System.err.println("SYNTAX_ERRORS=" + errs[0]);
        System.out.println(sb);
    }

    static void dump(ParseTree t, Parser p, StringBuilder sb) {
        if (t instanceof ParserRuleContext) {
            ParserRuleContext c = (ParserRuleContext) t;
            String rule = p.getRuleNames()[c.getRuleIndex()];
            int line = c.getStart() != null ? c.getStart().getLine() : -1;
            int endLine = c.getStop() != null ? c.getStop().getLine() : line;
            sb.append("{\"r\":\"").append(rule).append("\",\"ln\":").append(line)
              .append(",\"le\":").append(endLine).append(",\"k\":[");
            for (int i = 0; i < c.getChildCount(); i++) {
                if (i > 0) sb.append(",");
                dump(c.getChild(i), p, sb);
            }
            sb.append("]}");
        } else {
            sb.append("\"").append(esc(t.getText())).append("\"");
        }
    }

    static String esc(String s) {
        StringBuilder b = new StringBuilder();
        for (int i = 0; i < s.length(); i++) {
            char ch = s.charAt(i);
            if (ch == '"' || ch == '\\') b.append('\\').append(ch);
            else if (ch == '\n') b.append("\\n");
            else if (ch == '\r') {}
            else if (ch == '\t') b.append("\\t");
            else if (ch < 0x20) b.append(' ');
            else b.append(ch);
        }
        return b.toString();
    }
}
