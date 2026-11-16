package ai.chloe.voicelab.conversation;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** A named Korean maker question bound to testimony in the current conversation window. */
final class AppCreatorRecall {
    private static final String WORD = "[가-힣A-Za-z0-9_+.-]";
    private static final String BARE = "[가-힣A-Za-z0-9]" + WORD + "{0,39}?";
    private static final String TEXT = WORD + "(?:[가-힣A-Za-z0-9_+. \\-]{0,38}" + WORD + ")?";
    static final String QUOTED_TITLE = "(?:\"" + TEXT + "\"|“" + TEXT + "”|‘" + TEXT + "’|'" + TEXT + "'|「" + TEXT + "」)";
    private static final String NAME = "(?<title>" + QUOTED_TITLE + "|" + BARE + ")";
    private static final String TITLE = NAME + "(?<app>(?:이?라는)? 앱)?";
    private static final String PREFIX = "^(?:(?:그럼|그러면|혹시|(?:전에|아까|방금) (?:말한|말씀드린)) )?";
    // Only a topic marker may intervene. A quoted request, a second title or a
    // correction between the reference and the predicate cannot bind by accident.
    private static final String TOPIC_FRAME = "(?:(?:말이야|말이에요|말인데(?:요)?|얘긴데(?:요)?|있잖아(?:요)?)[.,!?]? +)?";
    private static final String ADVERB = "(?:(?:처음(?:에)?|원래|직접|혹시) +)?";
    private static final String END = "[?？.!]?$";
    private static final String MAKER_VERB = "(?:만들었|개발했|제작했)";
    private static final String ASK = "(?:어|어요|나요|니|지|죠|더라|더라구요|더라고요|던가요)";
    private static final String RECALL = "(?:기억(?:나|나요|해|하세요)|알(?:아|아요|고 있(?:어|어요|나요))|알려 ?(?:줘|주세요|줄래|줄래요))";
    private static final String WHO = "(?:누구(?:야|예요|에요|인가요|지|죠|였지|였죠|였나요|였더라)"
        + "|(?:누구(?:인지|였는지)|누군지) " + RECALL + "|누구라고 했(?:지|죠|나요)"
        + "|어느 (?:분|사람)(?:이었(?:지|죠|나요)|인가요|이야|이에요))";
    private static final String MADE = "(?:만든|개발한|제작한)";
    private static final String MAKER = "(?:개발자|제작자|선보인 (?:개발자|제작자)|"
        + "(?:개발|제작)을 맡은 (?:사람|분)|" + MADE + " (?:사람|분|게|건))";
    private static final String TARGET_FIRST = TITLE + "(?<post>은|는|을|를|의|,)? +";
    private static final Pattern BY_TITLE = Pattern.compile(PREFIX + TARGET_FIRST + TOPIC_FRAME + ADVERB + "(?:"
        + MAKER + "(?:은|는|이|가)? " + WHO
        + "|누가 " + MAKER_VERB + "(?:" + ASK + "|는지 " + RECALL + ")"
        + "|누가 " + MADE + " (?:앱|거)(?:이야|야|예요|인가요|였지|였죠|였나요|였더라|였어|였어요)"
        + "|(?:내가|제가) " + MAKER_VERB + "(?:지|나요|다고 했(?:지|죠|나요))"
        + "|" + MAKER + "(?:를|을|가)? " + RECALL + ")" + END);
    private static final Pattern BY_PERSON = Pattern.compile(PREFIX + "누가 " + TITLE
        + "(?<post>을|를)? " + MAKER_VERB + "(?:" + ASK + "|는지 " + RECALL + ")" + END);
    private static final Pattern[] QUESTIONS = {BY_TITLE, BY_PERSON};
    private static final Pattern NON_TITLES = Pattern.compile("너|널|나|날|내|제|저|당신|우리|이|그|이거|그거|이것|그것|앱");
    private static final Pattern POSSIBLE_TESTIMONY = Pattern.compile(
        "앱|제작|개발|만들|만든|만드|정정|취소|바뀌|바뀌었|아니|이름이 같|그건|그거");
    private static final Pattern CREATOR_CUE = Pattern.compile("개발|제작|만든|만들었|만드셨");
    private static final Pattern WHO_CUE = Pattern.compile("누구|누가|누군|어느 분");
    private static final String STATEMENT_END = MAKER_VERB + "(?:어|어요|습니다)[.!。]?$";
    private static final Pattern[] NAMED_CREATION = {
        Pattern.compile("^" + NAME + " 앱(?:은|을) (?:내가|제가) (?:직접 )?" + STATEMENT_END),
        Pattern.compile("^(?:내가|제가) " + NAME + " 앱을 (?:직접 )?" + STATEMENT_END)
    };

    enum Relation { USER_CREATED, NAME_ONLY, DIFFERENT_APP, AMBIGUOUS_ENDING, UNRESOLVED }

    final String title;
    final int source;
    final Relation relation;

    private AppCreatorRecall(String title, int source, Relation relation) {
        this.title = title;
        this.source = source;
        this.relation = relation;
    }

    static String unquote(String title) {
        return "\"“‘'「".indexOf(title.charAt(0)) >= 0 ? title.substring(1, title.length() - 1) : title;
    }

    private static final class Reference {
        final String title;
        final String wholeWord;
        final boolean typed;
        final boolean demonstrative;

        Reference(Matcher match) {
            String spelling = match.group("title");
            typed = match.group("app") != null;
            demonstrative = typed && (spelling.equals("그") || spelling.equals("이"));
            String bare = unquote(spelling);
            String post = match.group("post");
            String whole = !typed && bare.equals(spelling) && post != null && !post.equals(",") ? bare + post : null;
            // Korean 을/은 follow a final consonant and 를/는 a vowel. An
            // incompatible ending belongs to the title, not to a case marker.
            char last = bare.charAt(bare.length() - 1);
            boolean hangul = last >= 0xac00 && last <= 0xd7a3;
            boolean coda = (last - 0xac00) % 28 != 0;
            boolean incompatible = whole != null && hangul &&
                ((("을".equals(post) || "은".equals(post)) && !coda)
                || (("를".equals(post) || "는".equals(post)) && coda));
            title = incompatible ? whole : bare;
            wholeWord = incompatible ? null : whole;
        }

        String namedTitle(JSONArray rows, int end) throws Exception {
            if (wholeWord == null) return title;
            boolean wholeKnown = false, stemKnown = false;
            for (int i = 1; i < end; i++) {
                JSONObject row = rows.getJSONObject(i);
                if (!row.getString("role").equals("user")) continue;
                String text = row.getString("content").trim();
                String stated = createdTitle(text);
                if ("앱".equals(GroundedConversationPolicy.factTopic(text))) {
                    stated = GroundedConversationPolicy.sourceNames(text).get(0);
                }
                wholeKnown |= wholeWord.equals(stated);
                stemKnown |= title.equals(stated);
            }
            if (wholeKnown && stemKnown) return null;
            return wholeKnown ? wholeWord : title;
        }
    }

    private static Reference parse(String input) {
        String text = input.trim();
        for (Pattern pattern : QUESTIONS) {
            Matcher m = pattern.matcher(text);
            if (m.matches()) {
                Reference ref = new Reference(m);
                if (!ref.demonstrative && NON_TITLES.matcher(m.group("title")).matches()) return null;
                return ref;
            }
        }
        return null;
    }

    static boolean isQuestion(String input) {
        return parse(input) != null;
    }

    static boolean asksAboutMaker(String text) {
        return CREATOR_CUE.matcher(text).find() && WHO_CUE.matcher(text).find();
    }

    private static String createdTitle(String text) {
        for (Pattern pattern : NAMED_CREATION) {
            Matcher m = pattern.matcher(text);
            if (m.matches()) return unquote(m.group("title"));
        }
        return null;
    }

    /** A demonstrative follows the user's latest app reference, including a question about
     * a different app. Assistant guesses do not establish or rename the referent. */
    private static String previousTitle(JSONArray rows) throws Exception {
        for (int i = rows.length() - 2; i > 0; i--) {
            JSONObject row = rows.getJSONObject(i);
            if (!row.getString("role").equals("user")) continue;
            String text = row.getString("content").trim();
            Reference previous = parse(text);
            if (previous != null) {
                if (previous.demonstrative) continue;
                return previous.namedTitle(rows, i);
            }
            if ("앱".equals(GroundedConversationPolicy.factTopic(text))) {
                return GroundedConversationPolicy.sourceNames(text).get(0);
            }
            return createdTitle(text);
        }
        return null;
    }

    static AppCreatorRecall find(JSONArray rows, String question) throws Exception {
        Reference ref = parse(question);
        if (ref == null) return null;
        String title = ref.demonstrative ? previousTitle(rows) : ref.namedTitle(rows, rows.length() - 1);
        AppCreatorRecall unresolved = new AppCreatorRecall(title, -1, Relation.UNRESOLVED);
        if (title == null) return unresolved;

        int latestApp = -1;
        int namedMatch = -1;
        boolean sawNamedApp = false;
        boolean earlierMatch = false;
        boolean otherTestimony = false;
        for (int i = 1; i < rows.length() - 1; i++) {
            JSONObject row = rows.getJSONObject(i);
            if (!row.getString("role").equals("user")) continue;
            String text = row.getString("content").trim();
            if (isQuestion(text)) continue;
            String created = createdTitle(text);
            if (created != null) {
                sawNamedApp = true;
                if (created.equals(title)) namedMatch = i;
                continue;
            }
            String topic = GroundedConversationPolicy.factTopic(text);
            if ("앱".equals(topic)) {
                latestApp = i;
                if (GroundedConversationPolicy.sourceNames(text).contains(title)) earlierMatch = true;
            } else if (topic != null) {
                if (!ref.typed && (GroundedConversationPolicy.sourceNames(text).contains(title)
                    || ("물건".equals(topic) && GroundedConversationPolicy.mentions(text, title)))) return unresolved;
            } else if (text.contains(title) || POSSIBLE_TESTIMONY.matcher(text).find()) {
                // Unparsed testimony may name a third-party maker, retract or correct a
                // statement. Leave it in history instead of overriding it with a guess.
                latestApp = -1;
                namedMatch = -1;
                otherTestimony = true;
            }
        }
        if (namedMatch >= 0) return new AppCreatorRecall(title, namedMatch, Relation.USER_CREATED);
        // A bare name after a topic switch need not be another app. Decline an
        // unknown-title override unless the question or recent user focus supplies that scope.
        boolean appContext = ref.typed || previousTitle(rows) != null;
        if (latestApp < 0) return sawNamedApp && appContext && !otherTestimony
            ? new AppCreatorRecall(title, -1, Relation.DIFFERENT_APP) : unresolved;
        String text = rows.getJSONObject(latestApp).getString("content").trim();
        List<String> names = GroundedConversationPolicy.sourceNames(text);
        int index = names.indexOf(title);
        if (index < 0) {
            return earlierMatch || otherTestimony || !appContext ? unresolved : new AppCreatorRecall(title, -1, Relation.DIFFERENT_APP);
        }
        if (index > 0) return new AppCreatorRecall(title, -1, Relation.AMBIGUOUS_ENDING);
        if (GroundedConversationPolicy.explicitCreator(text)) {
            return new AppCreatorRecall(title, latestApp, Relation.USER_CREATED);
        }
        return otherTestimony ? unresolved : new AppCreatorRecall(title, latestApp, Relation.NAME_ONLY);
    }

    String hint() throws Exception {
        if (relation == Relation.UNRESOLVED) return "";
        JSONObject reference = new JSONObject().put("question_app", title);
        if (source >= 0) reference.put("source_user_message", source);
        switch (relation) {
            case USER_CREATED: return "\n질문이 가리키는 이 앱은 사용자가 직접 만들었다고 밝혔다. " + reference;
            case NAME_ONLY: return "\n이 앱의 이름은 사용자가 알려 주었다. 제작자는 그 진술에서 확인되지 않는다. " + reference;
            case DIFFERENT_APP: return "\n질문한 이름은 앞서 알려 준 앱과 다르며, 이 이름의 제작자는 대화에서 확인되지 않는다. " + reference;
            case AMBIGUOUS_ENDING: return "\n사용자가 말한 이름의 어미가 모호해서 같은 앱인지 확정할 수 없다. " + reference;
            default: throw new AssertionError(relation);
        }
    }

    GroundedConversationPolicy.Decision answer(boolean polite) {
        switch (relation) {
            case USER_CREATED: return new GroundedConversationPolicy.Decision("grounded_app_creator", polite
                ? "그 앱은 직접 만드셨다고 말씀하셨어요." : "그 앱은 네가 직접 만들었다고 했어.");
            case NAME_ONLY: return new GroundedConversationPolicy.Decision("app_creator_unspecified", polite
                ? "앱 이름은 알려 주셨지만, 누가 만들었는지는 그 말씀만으로 알 수 없어요."
                : "앱 이름은 알려 줬지만, 누가 만들었는지는 그 말만으로 알 수 없어.");
            case DIFFERENT_APP: return new GroundedConversationPolicy.Decision("app_creator_unknown_title",
                "‘" + title + "’의 제작자는 " + (polite ? "아직 모르겠어요." : "아직 몰라."));
            case AMBIGUOUS_ENDING: return new GroundedConversationPolicy.Decision("app_creator_uncertain_title",
                "‘" + title + "’와 앞서 " + (polite ? "말씀하신 앱이 같은 앱인지는 확실하지 않아요."
                    : "말한 앱이 같은 앱인지는 확실하지 않아."));
            case UNRESOLVED: return null;
            default: throw new AssertionError(relation);
        }
    }

}
