use backtrace::Backtrace;
use once_cell::sync::OnceCell;
use std::collections::{HashMap, HashSet};
use std::env;
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::os::raw::c_void;
use std::sync::{Mutex, RwLock};

static LOG_FILE: OnceCell<Mutex<File>> = OnceCell::new();
static SYMBOL_CACHE: OnceCell<RwLock<HashMap<usize, Option<String>>>> = OnceCell::new();
static SEEN_PAIRS: OnceCell<Mutex<HashSet<(Option<String>, Option<String>)>>> = OnceCell::new();
static LOGGING_ENABLED: OnceCell<Mutex<bool>> = OnceCell::new();

#[no_mangle]
pub extern "C" fn __cyg_profile_func_enter_fine_i_will_do_it_myself() {
    static INITIALIZED: std::sync::Once = std::sync::Once::new();
    INITIALIZED.call_once(|| {
        let logging_enabled = env::var("EXPORT_CALLS").is_ok();
        LOGGING_ENABLED
            .set(Mutex::new(logging_enabled))
            .expect("Failed to set logging enabled");
        if logging_enabled {
            initialize_logging();
        }
    });

    if !LOGGING_ENABLED.get().unwrap().lock().unwrap().clone() {
        return;
    }

    let current_bt = Backtrace::new_unresolved();
    let frames = current_bt.frames();

    let callee = frames.get(1).and_then(|frame| symbolize_pc(frame.ip()));
    let caller = frames
        .iter()
        .skip(2)
        .find_map(|frame| symbolize_pc(frame.ip()));

    let pair = (callee.clone(), caller.clone());
    if !SEEN_PAIRS
        .get()
        .expect("SEEN_PAIRS not initialized")
        .lock()
        .unwrap()
        .insert(pair)
    {
        return;
    }

    if let Some(log_file) = LOG_FILE.get() {
        let tid = unsafe { libc::syscall(libc::SYS_gettid) };
        let mut file = log_file.lock().expect("Failed to lock log file");
        let callee = callee.unwrap_or("<null>".to_string());
        let caller = caller.unwrap_or("<null>".to_string());
        writeln!(file, "{:?}|{}|{}", tid, callee, caller).expect("Failed to write to log file");
    }
}

#[inline]
fn symbolize_pc(pc: *mut c_void) -> Option<String> {
    let pc_usize = pc as usize;
    if let Some(cache) = SYMBOL_CACHE.get() {
        if let Some(symbol) = cache.read().unwrap().get(&pc_usize) {
            return symbol.clone();
        }
    }

    let symbol = __symbolize_pc(pc);
    if let Some(cache) = SYMBOL_CACHE.get() {
        cache.write().unwrap().insert(pc_usize, symbol.clone());
    }

    symbol
}

#[inline]
/// Mimics the behavior of `__sanitizer_symbolize_pc` from ASAN, but uses `backtrace` crate to resolve the symbol and return the function name.
fn __symbolize_pc(pc: *mut c_void) -> Option<String> {
    let mut result = None;
    backtrace::resolve(pc, |symbol| {
        if let Some(symbol_name) = symbol.name() {
            result = Some(symbol_name.to_string());
        }
    });
    result
}

fn initialize_logging() {
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

#[ctor::dtor]
fn cleanup() {
    if LOGGING_ENABLED.get().unwrap().lock().unwrap().clone() {
        if let Some(file) = LOG_FILE.get() {
            let _ = file.lock().unwrap().sync_all();
        }
    }
}
