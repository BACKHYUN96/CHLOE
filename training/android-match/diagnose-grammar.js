/* Exploratory diagnostic AFTER the unchanged application comparison.
 * Only the template-derived grammar's root changes; request messages, system
 * persona, schema, sampling, template/parser and model remain unchanged.
 * This is not a product fix or an upstream binary patch.
 */
(function () {
  var g = globalThis, api = g.__r(1740).LlamaContext.prototype;
  if (g.__chloeGrammarDiagnostic) return;
  g.__chloeGrammarDiagnostic = true;
  var original = api.getFormattedChat;
  api.getFormattedChat = function () {
    var args = Array.prototype.slice.call(arguments);
    return original.apply(this, args).then(function (value) {
      var params = args[2] || {};
      if (!params.response_format || params.enable_thinking !== false) return value;
      var old = value.grammar.match(/^root ::= .*$/m);
      if (!old || old[0].indexOf('response-format') < 0 || old[0].indexOf('im_start') < 0) {
        throw new Error('Unexpected grammar root; refusing diagnostic');
      }
      var root = 'root ::= response-format';
      var result = Object.assign({}, value, {grammar: value.grammar.replace(/^root ::= .*$/m, root)});
      g.nativeLoggingHook('CHLOE_MATCH_DIAGNOSTIC ' + JSON.stringify({old_root: old[0], new_root: root}), 1);
      return result;
    });
  };
  g.nativeLoggingHook('CHLOE_MATCH_DIAGNOSTIC ready', 1);
})();
