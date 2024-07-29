use libc::{c_char, syscall, SYS_gettid};
use once_cell::sync::OnceCell;
use std::collections::{HashMap, HashSet};
use std::env;
use std::ffi::CStr;
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::os::raw::c_void;
use std::sync::{Mutex, RwLock};

static LOG_FILE: OnceCell<Mutex<File>> = OnceCell::new();
static SYMBOL_CACHE: OnceCell<RwLock<HashMap<usize, String>>> = OnceCell::new();
static SEEN_PAIRS: OnceCell<Mutex<HashSet<(String, String)>>> = OnceCell::new();
static LOGGING_ENABLED: OnceCell<bool> = OnceCell::new();

#[no_mangle]
pub extern "C" fn __cyg_profile_func_enter(this_fn: *mut c_void, call_site: *mut c_void) {
    if !*LOGGING_ENABLED.get().unwrap_or(&false) {
        return;
    }
    let callee = symbolize_pc_cached((this_fn as usize + 0x1) as *mut c_void);
    let caller = symbolize_pc_cached(call_site);

    let pair = (callee.clone(), caller.clone());
    let mut seen_pairs = SEEN_PAIRS.get().unwrap().lock().unwrap();
    if !seen_pairs.insert(pair) {
        return;
    }

    if let Some(file) = LOG_FILE.get() {
        let tid = unsafe { syscall(SYS_gettid) };
        let mut file = file.lock().unwrap();
        writeln!(file, "{}|{}|{}", tid, callee, caller).expect("Failed to write to log file");
    }
}

#[no_mangle]
pub extern "C" fn __cyg_profile_func_exit(_: *mut c_void, _: *mut c_void) {
    // Intentionally left blank
}

fn symbolize_pc_cached(pc: *mut c_void) -> String {
    let pc_usize = pc as usize;
    if let Some(cache) = SYMBOL_CACHE.get() {
        if let Some(symbol) = cache.read().unwrap().get(&pc_usize) {
            return symbol.clone();
        }
    }

    let symbol = symbolize_pc(pc);
    if let Some(cache) = SYMBOL_CACHE.get() {
        cache.write().unwrap().insert(pc_usize, symbol.clone());
    }

    symbol
}

fn symbolize_pc(pc: *mut c_void) -> String {
    let mut buf = vec![0; 1024];
    unsafe {
        __sanitizer_symbolize_pc(
            pc,
            c"%f".as_ptr(),
            buf.as_mut_ptr() as *mut c_char,
            buf.len(),
        );
    }
    unsafe { CStr::from_ptr(buf.as_ptr() as *const c_char) }
        .to_string_lossy()
        .into_owned()
}

extern "C" {
    fn __sanitizer_symbolize_pc(
        pc: *mut c_void,
        fmt: *const c_char,
        out_buf: *mut c_char,
        out_buf_size: usize,
    );
}

#[ctor::ctor]
fn init() {
    let logging_enabled = env::var("EXPORT_CALLS").is_ok();
    LOGGING_ENABLED
        .set(logging_enabled)
        .expect("Failed to set logging enabled");

    if logging_enabled {
        let file = OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open("/tmp/callgraph.log")
            .expect("Failed to open log file");

        LOG_FILE
            .set(Mutex::new(file))
            .expect("Failed to set log file");
        SYMBOL_CACHE
            .set(RwLock::new(HashMap::new()))
            .expect("Failed to set symbol cache");
        SEEN_PAIRS
            .set(Mutex::new(HashSet::new()))
            .expect("Failed to set seen pairs");
    }
}

#[ctor::dtor]
fn cleanup() {
    if *LOGGING_ENABLED.get().unwrap_or(&false) {
        if let Some(file) = LOG_FILE.get() {
            let _ = file.lock().unwrap().sync_all();
        }
    }
}
