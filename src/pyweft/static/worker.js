// PyWeft background worker: a second Python, on its own browser thread, that
// runs run_in_background() calls so the page keeps responding. shell.html
// starts it on first use and sends it one call at a time.
//
// Messages in:  {type: "init", pyodideUrl, modules, appFiles, packages}
//               {type: "call", id, request}        request: Uint8Array
//               {type: "files", write: {name: text}, remove: [name]}
// Messages out: {type: "ready"} | {type: "failed", error}
//               {type: "reply", id, reply}         reply: Uint8Array
//               {type: "reply", id, error}         the interpreter failed

let pyodide = null;
let call = null;
let markReady;
const ready = new Promise((resolve) => (markReady = resolve));

function writeAppFile(name, text) {
  const dir = name.includes("/") ? name.slice(0, name.lastIndexOf("/")) : "";
  pyodide.FS.mkdirTree(dir ? `/app/${dir}` : "/app");
  pyodide.FS.writeFile(`/app/${name}`, text);
}

async function init({ pyodideUrl, modules, appFiles, packages }) {
  importScripts(pyodideUrl);
  pyodide = await loadPyodide();
  if (packages.length) {
    await pyodide.loadPackage("micropip");
    await pyodide.pyimport("micropip").install(pyodide.toPy(packages));
  }
  pyodide.FS.mkdirTree("/pyweft-src/pyweft");
  for (const name of modules) {
    const src = await (await fetch(`pyweft-src/${name}`)).text();
    pyodide.FS.writeFile(`/pyweft-src/pyweft/${name}`, src);
  }
  for (const name of appFiles) {
    writeAppFile(name, await (await fetch(`app/${name}`)).text());
  }
  pyodide.runPython(`
import sys
sys.path.insert(0, "/pyweft-src")

def pyweft_worker_call(request):
    from pyodide.ffi import to_js
    from pyweft.background import execute
    return to_js(execute(request.to_bytes()))
`);
  call = pyodide.globals.get("pyweft_worker_call");
}

self.onmessage = async ({ data }) => {
  if (data.type === "init") {
    try {
      await init(data);
      markReady();
      self.postMessage({ type: "ready" });
    } catch (err) {
      self.postMessage({ type: "failed", error: String(err?.message ?? err) });
    }
    return;
  }
  // Anything else waits for init, so a file update cannot be overwritten by
  // the older copy init fetched.
  await ready;
  if (data.type === "files") {
    for (const [name, text] of Object.entries(data.write)) writeAppFile(name, text);
    for (const name of data.remove) {
      try { pyodide.FS.unlink(`/app/${name}`); } catch {}
    }
  } else if (data.type === "call") {
    let reply;
    try {
      // execute() itself never raises: the function's errors come back
      // inside the reply. This catches the interpreter failing.
      // slice(): a compact copy we own, so its buffer can be transferred.
      reply = call(data.request).slice();
    } catch (err) {
      self.postMessage({ type: "reply", id: data.id, error: String(err?.message ?? err) });
      return;
    }
    self.postMessage({ type: "reply", id: data.id, reply }, [reply.buffer]);
  }
};
