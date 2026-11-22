//! The `spskit-vit1` command line: attach a captured module read as the VIT1 programming-data block.
//!
//! Offline only. A captured `voltkit profile --clone` file and a VIN in, a request body out. Nothing
//! here opens a socket, posts to TDS, reads a dongle, or programs a vehicle. The interface matches
//! the Python original `vcxtoolkit`'s `collect` references: `spskit-vit1 --read <file> --code <K17>
//! --vin <VIN> [--ecu NAME] [--ssecuhn S] [--cvn 0|1] [--partnum P ...] [--template body.json]
//! [--out FILE]`.

use std::process::ExitCode;

use spskit::handoff::{request_from_read, vit1_from_read};
use spskit::vit1::read_codes;

const USAGE: &str = "usage: spskit-vit1 --read <clone.txt> --code <CODE> [--vin VIN] [--ecu NAME] \
[--ssecuhn S] [--cvn 0|1] [--partnum P ...] [--template body.json] [--out FILE]";

fn main() -> ExitCode {
    let args: Vec<String> = std::env::args().skip(1).collect();
    ExitCode::from(run(&args))
}

struct Options {
    read: String,
    code: String,
    vin: String,
    ecu: Option<String>,
    ssecuhn: Option<String>,
    cvn: Option<String>,
    partnums: Vec<String>,
    template: Option<String>,
    out: Option<String>,
}

fn run(args: &[String]) -> u8 {
    let options = match parse_args(args) {
        Ok(options) => options,
        Err(message) => {
            eprintln!("{message}\n{USAGE}");
            return 2;
        }
    };
    execute(&options)
}

fn execute(options: &Options) -> u8 {
    let text = match std::fs::read_to_string(&options.read) {
        Ok(text) => text,
        Err(err) => {
            eprintln!("{}: {err}", options.read);
            return 2;
        }
    };
    let partnums = options.partnums.clone();
    let body = if let Some(template_path) = &options.template {
        let template_text = match std::fs::read_to_string(template_path) {
            Ok(text) => text,
            Err(err) => {
                eprintln!("{template_path}: {err}");
                return 2;
            }
        };
        let template = match serde_json::from_str(&template_text) {
            Ok(value) => value,
            Err(err) => {
                eprintln!("{template_path}: {err}");
                return 2;
            }
        };
        request_from_read(
            &text,
            &template,
            &options.code,
            &options.vin,
            options.ecu.as_deref(),
            options.ssecuhn.as_deref(),
            options.cvn.as_deref(),
            &partnums,
        )
    } else {
        vit1_from_read(
            &text,
            &options.code,
            &options.vin,
            options.ecu.as_deref(),
            options.ssecuhn.as_deref(),
            options.cvn.as_deref(),
            &partnums,
        )
    };
    let body = match body {
        Ok(body) => body,
        Err(err) => {
            eprintln!("{err}");
            return 2;
        }
    };
    let rendered = serde_json::to_string_pretty(&body).expect("a request body serializes");
    if let Some(out) = &options.out {
        if let Err(err) = std::fs::write(out, format!("{rendered}\n")) {
            eprintln!("{out}: {err}");
            return 2;
        }
        eprintln!("wrote {out}");
    } else {
        println!("{rendered}");
    }
    0
}

fn parse_args(args: &[String]) -> std::result::Result<Options, String> {
    let mut read: Option<String> = None;
    let mut code: Option<String> = None;
    let mut vin = String::new();
    let mut ecu = None;
    let mut ssecuhn = None;
    let mut cvn = None;
    let mut partnums = Vec::new();
    let mut template = None;
    let mut out = None;
    let mut iter = args.iter();
    while let Some(flag) = iter.next() {
        let mut take = |name: &str| -> std::result::Result<String, String> {
            iter.next()
                .cloned()
                .ok_or_else(|| format!("{name} needs a value"))
        };
        match flag.as_str() {
            "--read" => read = Some(take("--read")?),
            "--code" => code = Some(take("--code")?),
            "--vin" => vin = take("--vin")?,
            "--ecu" => ecu = Some(take("--ecu")?),
            "--ssecuhn" => ssecuhn = Some(take("--ssecuhn")?),
            "--cvn" => {
                let value = take("--cvn")?;
                if value != "0" && value != "1" {
                    return Err("--cvn is 0 or 1".to_owned());
                }
                cvn = Some(value);
            }
            "--partnum" => partnums.push(take("--partnum")?),
            "--template" => template = Some(take("--template")?),
            "--out" => out = Some(take("--out")?),
            "-h" | "--help" => return Err("spskit-vit1".to_owned()),
            other => return Err(format!("unknown argument: {other}")),
        }
    }
    let Some(read) = read else {
        return Err("--read is required".to_owned());
    };
    let Some(code) = code else {
        return Err(format!(
            "--code is required, one of: {}",
            read_codes().join(", ")
        ));
    };
    Ok(Options {
        read,
        code,
        vin,
        ecu,
        ssecuhn,
        cvn,
        partnums,
        template,
        out,
    })
}
