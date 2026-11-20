//! Pequenas utilidades de sistema.

use std::time::{SystemTime, UNIX_EPOCH};

/// Não abre janela de console no Windows ao rodar programas auxiliares.
pub fn hide_console(cmd: &mut tokio::process::Command) {
    #[cfg(windows)]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    #[cfg(not(windows))]
    let _ = cmd;
}

/// (total, disponível) de RAM em MB.
pub fn system_memory_mb() -> (u64, u64) {
    #[cfg(target_os = "linux")]
    {
        if let Ok(text) = std::fs::read_to_string("/proc/meminfo") {
            return parse_meminfo(&text);
        }
        (0, 0)
    }
    #[cfg(windows)]
    {
        use windows::Win32::System::SystemInformation::{GlobalMemoryStatusEx, MEMORYSTATUSEX};
        let mut st = MEMORYSTATUSEX { dwLength: std::mem::size_of::<MEMORYSTATUSEX>() as u32, ..Default::default() };
        unsafe {
            if GlobalMemoryStatusEx(&mut st).is_ok() {
                return (st.ullTotalPhys / (1024 * 1024), st.ullAvailPhys / (1024 * 1024));
            }
        }
        (0, 0)
    }
    #[cfg(not(any(target_os = "linux", windows)))]
    {
        (0, 0)
    }
}

pub fn parse_meminfo(text: &str) -> (u64, u64) {
    let mut total = 0;
    let mut avail = 0;
    for line in text.lines() {
        let mut it = line.split_whitespace();
        match (it.next(), it.next()) {
            (Some("MemTotal:"), Some(v)) => total = v.parse::<u64>().unwrap_or(0) / 1024,
            (Some("MemAvailable:"), Some(v)) => avail = v.parse::<u64>().unwrap_or(0) / 1024,
            _ => {}
        }
    }
    (total, avail)
}

pub fn now_unix() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0)
}

pub fn now_millis() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_millis() as u64).unwrap_or(0)
}

/// Tamanho legível em português ("1,8 GB").
pub fn human_size(bytes: u64) -> String {
    const GB: f64 = 1024.0 * 1024.0 * 1024.0;
    const MB: f64 = 1024.0 * 1024.0;
    let b = bytes as f64;
    let s = if b >= GB { format!("{:.1} GB", b / GB) } else { format!("{:.0} MB", b / MB) };
    s.replace('.', ",")
}

/// Porta livre em 127.0.0.1 (para o llama-server interno).
pub fn free_local_port() -> std::io::Result<u16> {
    let l = std::net::TcpListener::bind(("127.0.0.1", 0))?;
    Ok(l.local_addr()?.port())
}

/// Nome de arquivo seguro a partir de um texto qualquer.
pub fn safe_file_name(s: &str) -> String {
    let mut out: String = s.chars().map(|c| if c.is_ascii_alphanumeric() || matches!(c, '.' | '-' | '_') { c } else { '_' }).collect();
    while out.starts_with('.') {
        out.remove(0);
    }
    if out.is_empty() {
        out.push_str("modelo");
    }
    out.truncate(120);
    out
}

/// Tamanho total de uma pasta (recursivo; ignora o que não conseguir ler).
pub fn dir_size(dir: &std::path::Path) -> u64 {
    let Ok(rd) = std::fs::read_dir(dir) else { return 0 };
    rd.flatten()
        .map(|e| match e.file_type() {
            Ok(t) if t.is_dir() => dir_size(&e.path()),
            Ok(_) => e.metadata().map(|m| m.len()).unwrap_or(0),
            Err(_) => 0,
        })
        .sum()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn meminfo() {
        let (t, a) = parse_meminfo("MemTotal:       16303428 kB\nMemFree:  100 kB\nMemAvailable:   12000000 kB\n");
        assert_eq!(t, 15921);
        assert_eq!(a, 11718);
    }

    #[test]
    fn tamanho_legivel() {
        assert_eq!(human_size(639_446_688), "610 MB");
        assert_eq!(human_size(5_027_783_488), "4,7 GB");
    }

    #[test]
    fn nome_seguro() {
        assert_eq!(safe_file_name("../library/llama3.2:3b"), "_library_llama3.2_3b");
        assert_eq!(safe_file_name(""), "modelo");
    }
}

/// Data e hora em UTC no formato ISO 8601 ("2026-11-20T22:10:05Z").
pub fn iso_utc(unix: u64) -> String {
    let dias = (unix / 86_400) as i64;
    let resto = unix % 86_400;
    // Algoritmo "civil from days" (Howard Hinnant), sem depender de biblioteca de datas.
    let z = dias + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z.rem_euclid(146_097);
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let dia = doy - (153 * mp + 2) / 5 + 1;
    let mes = if mp < 10 { mp + 3 } else { mp - 9 };
    let ano = yoe + era * 400 + i64::from(mes <= 2);
    format!("{ano:04}-{mes:02}-{dia:02}T{:02}:{:02}:{:02}Z", resto / 3600, (resto % 3600) / 60, resto % 60)
}

/// Agora, em ISO 8601 UTC.
pub fn agora_iso() -> String {
    iso_utc(now_unix())
}

/// Identificador aleatório em hexadecimal (`bytes` × 2 caracteres). Não serve para senha forte.
pub fn id_aleatorio(bytes: usize) -> String {
    use std::collections::hash_map::RandomState;
    use std::hash::{BuildHasher, Hasher};
    use std::sync::atomic::{AtomicU64, Ordering};
    static CONTADOR: AtomicU64 = AtomicU64::new(0);
    let mut s = String::new();
    while s.len() < bytes * 2 {
        let mut h = RandomState::new().build_hasher();
        h.write_u64(now_millis());
        h.write_u64(CONTADOR.fetch_add(1, Ordering::Relaxed));
        h.write_u32(std::process::id());
        s.push_str(&format!("{:016x}", h.finish()));
    }
    s.truncate(bytes * 2);
    s
}

/// Mescla `patch` em `alvo` seguindo o JSON Merge Patch (RFC 7386):
/// objetos se mesclam, `null` apaga o campo e o resto substitui.
pub fn merge_patch(alvo: &mut serde_json::Value, patch: &serde_json::Value) {
    use serde_json::Value;
    let Value::Object(p) = patch else {
        *alvo = patch.clone();
        return;
    };
    if !alvo.is_object() {
        *alvo = Value::Object(Default::default());
    }
    let obj = alvo.as_object_mut().expect("acabou de virar objeto");
    for (k, v) in p {
        if v.is_null() {
            obj.remove(k);
        } else {
            merge_patch(obj.entry(k.clone()).or_insert(Value::Null), v);
        }
    }
}

#[cfg(test)]
mod tests_merge {
    use super::*;
    use serde_json::json;

    #[test]
    fn exemplos_da_rfc_7386() {
        let casos = [
            (json!({"a": "b"}), json!({"a": "c"}), json!({"a": "c"})),
            (json!({"a": "b"}), json!({"b": "c"}), json!({"a": "b", "b": "c"})),
            (json!({"a": "b"}), json!({"a": null}), json!({})),
            (json!({"a": ["b"]}), json!({"a": "c"}), json!({"a": "c"})),
            (json!({"a": "c"}), json!({"a": ["b"]}), json!({"a": ["b"]})),
            (json!({"a": {"b": "c"}}), json!({"a": {"b": "d", "c": null}}), json!({"a": {"b": "d"}})),
            (json!(["a", "b"]), json!(["c", "d"]), json!(["c", "d"])),
            (json!({"a": "foo"}), json!(null), json!(null)),
            (json!({"e": null}), json!({"a": 1}), json!({"e": null, "a": 1})),
            (json!([1, 2]), json!({"a": "b", "c": null}), json!({"a": "b"})),
        ];
        for (mut alvo, patch, esperado) in casos {
            merge_patch(&mut alvo, &patch);
            assert_eq!(alvo, esperado, "patch {patch}");
        }
    }

    #[test]
    fn ids_nao_se_repetem() {
        let a = id_aleatorio(8);
        let b = id_aleatorio(8);
        assert_eq!(a.len(), 16);
        assert_ne!(a, b);
    }
}
