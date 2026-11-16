/* Observation only, loaded into the synthetic-data comparison package.
 * Delegate unchanged arguments and return the original native promise/result.
 * No output repair, sampler/prompt alteration or extra inference is performed.
 */
(function () {
  var global = globalThis;
  if (global.__chloeMatchObserver) return;
  global.__chloeMatchObserver = true;
  var serial = 0;
  function emit(event, name, id, value) {
    var text = JSON.stringify(value);
    if (text === undefined) text = 'null';
    var total = Math.ceil(text.length / 500);
    for (var i = 0; i < total; i++) {
      global.nativeLoggingHook('CHLOE_MATCH_OBS ' + JSON.stringify({
        event: event, name: name, id: id, part: i, total: total,
        text: text.slice(i * 500, (i + 1) * 500)
      }), 1);
    }
  }
  // This module number was diagnosed in an excluded cold-start probe, then
  // used alone after restart. It is specific to the recorded 1.22.0 APK hash.
  // llama.rn removes its temporary global JSI bindings after installation.
  var module = global.__r(1740);
  var api = module.LlamaContext.prototype;
  ['getFormattedChat', 'completion'].forEach(function (name) {
    var original = api[name];
    if (typeof original !== 'function') { emit('missing', name, 0, null); return; }
    api[name] = function () {
      var args = Array.prototype.slice.call(arguments), id = ++serial;
      if (name === 'completion') {
        emit('context', name, id, {gpu: this.gpu, devices: this.devices,
          reasonNoGPU: this.reasonNoGPU, androidLib: this.androidLib, systemInfo: this.systemInfo});
      }
      emit('call', name, id, args);
      var result = original.apply(this, args);
      if (result && typeof result.then === 'function') {
        result.then(function (value) { emit('result', name, id, value); },
                    function (error) { emit('error', name, id, String(error)); });
      } else { emit('result', name, id, result); }
      return result;
    };
  });
  emit('ready', 'observer', 0, {build: module.BuildInfo});
})();
