use backtrace::Backtrace;
use dashmap::{DashMap, DashSet};
use lazy_static::lazy_static;
use std::cell::Cell;
use std::env;
use std::fs::{File, OpenOptions};
use std::io::Write;
use std::os::raw::c_void;
use std::sync::Mutex;

type FunctionName = Option<String>;
type FunctionPair = (FunctionName, FunctionName);

lazy_static! {
    static ref ENABLED: bool = env::var("EXPORT_CALLS").is_ok();
    static ref LOG_FILE: Mutex<Option<File>> = Mutex::new(None);
    static ref SEEN_PAIRS: DashSet<FunctionPair> = DashSet::new();
    static ref SYMBOL_CACHE: DashMap<usize, FunctionName> = DashMap::new();
}

// This is a thread-local variable that prevents recursion.
// Without it, we could get infinite recursion:
// When cyg_profile_func_enter calls libC function like write() to log a call,
// if write() is also instrumented (or replaced by a instrumented wrapper), it triggers cyg_profile_func_enter again,
// creating an infinite loop that would crash with stack overflow.
thread_local! {
    static PREVENT_RECURSION: Cell<bool> = const { Cell::new(false) };
}

struct RecursionGuard;

impl RecursionGuard {
    fn new() -> Self {
        PREVENT_RECURSION.set(true);
        RecursionGuard
    }
}

impl Drop for RecursionGuard {
    fn drop(&mut self) {
        PREVENT_RECURSION.set(false);
    }
}

#[no_mangle]
pub extern "C" fn __seedmind_func_enter() {
    if !*ENABLED {
        return;
    }

    if PREVENT_RECURSION.get() {
        eprintln!("Recursion detected in __seedmind_func_enter");
        return;
    }

    // create a guard that will automatically set PREVENT_RECURSION to false when it goes out of scope
    let _guard = RecursionGuard::new();

    static INITIALIZED: std::sync::Once = std::sync::Once::new();
    INITIALIZED.call_once(|| {
        if *ENABLED {
            initialize_logging();
        }
    });

    let current_bt = Backtrace::new_unresolved();
    let frames = current_bt.frames();

    let callee = frames.get(1).and_then(|frame| symbolize_pc(frame.ip()));
    let caller = frames
        .iter()
        .skip(2)
        .find_map(|frame| symbolize_pc(frame.ip()));

    let pair = (callee.clone(), caller.clone());
    if !SEEN_PAIRS.insert(pair) {
        // insert returns false means the hashset already has this pair.
        return;
    }

    if let Some(file) = &mut *LOG_FILE.lock().expect("Failed to lock log file") {
        let tid = unsafe { libc::syscall(libc::SYS_gettid) };
        let callee = callee.unwrap_or("<null>".to_string());
        let caller = caller.unwrap_or("<null>".to_string());
        writeln!(file, "{:?}|{}|{}", tid, callee, caller).expect("Failed to write to log file");
        let _ = file.sync_all();
    }
}

#[inline]
fn symbolize_pc(pc: *mut c_void) -> Option<String> {
    let pc_usize = pc as usize;
    if let Some(cache) = SYMBOL_CACHE.get(&pc_usize) {
        return cache.clone();
    }

    let symbol = __symbolize_pc(pc);
    SYMBOL_CACHE.insert(pc_usize, symbol.clone());

    symbol
}

#[inline]
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

    *LOG_FILE.lock().expect("Failed to lock log file") = Some(file);
}
