// Renders FeatureExtraction's aggregated covariate SQL for the presets in a settings file and
// translates it to each target dialect. Run by tools/render_feature_extraction.py, which pins the
// jars; nothing here runs in DSS.
//
//   java -cp <featureExtraction.jar>:<json.jar>:<SqlRender.jar> Render.java <settings.json> \
//        <cohort_table> <cdm_database_schema> <session_id> <dialect>[=<temp_emulation_schema>]...
//
// A dialect given with a temp emulation schema (spark) gets real tables in that schema in place of
// temp tables; the others keep their native temp tables.
//
// Prints one JSON object: {"<dialect>": {"<part>": "<sql>", ...}, ...}. The parts are those of
// FeatureExtraction.createSql (the same call the FeatureExtraction R package makes), in the SQL
// Server dialect, then translated with SqlRender.

import org.json.JSONObject;
import org.ohdsi.featureExtraction.FeatureExtraction;
import org.ohdsi.sql.SqlTranslate;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;

public class Render {
    static final String[] PARTS = {"sqlConstruction", "sqlQueryFeatures", "sqlQueryContinuousFeatures",
            "sqlQueryFeatureRef", "sqlQueryAnalysisRef", "sqlCleanup"};

    public static void main(String[] args) throws Exception {
        if (args.length < 5) {
            System.err.println("usage: Render <settings.json> <cohort_table> <cdm_database_schema> <session_id> <dialect>[=<temp_schema>]...");
            System.exit(2);
        }
        String settings = new String(Files.readAllBytes(Paths.get(args[0])), StandardCharsets.UTF_8);
        FeatureExtraction.init(null); // the templates and CSV files inside the jar
        JSONObject todo = new JSONObject(FeatureExtraction.createSql(settings, true, args[1], "subject_id",
                new String[] {"-1"}, args[2], "0", "0"));
        if (todo.getJSONObject("tempTables").length() != 0)
            throw new IllegalStateException("the settings need temp tables of concept ids, which this renderer does not write");
        JSONObject out = new JSONObject();
        for (int i = 4; i < args.length; i++) {
            String[] spec = args[i].split("=", 2);
            String tempSchema = spec.length == 2 ? spec[1] : null;
            JSONObject dialect = new JSONObject();
            for (String part : PARTS)
                dialect.put(part, SqlTranslate.translateSql(todo.getString(part), spec[0], args[3], tempSchema));
            out.put(spec[0], dialect);
        }
        System.out.println(out.toString());
    }
}
