//! The GM wrapper contract `spsvcs` asks for by name.
//!
//! This module does not load a library, open a registry key, or speak SAE J2534. `CSpsVcsImpl::Init`
//! reads `SOFTWARE\GM\J2534Wrapper` value `FunctionLibrary` and resolves the four exports below on
//! that file. The file was not on the analysed machine. `spsvcs.dll` also exports the same four
//! names as its own API. The port classifies the connect string into the forms `Init` logs; it
//! resolves nothing and loads nothing.

use crate::error::{Error, Result};

/// The registry key `CSpsVcsImpl::Init` reads for the wrapper library path.
pub const WRAPPER_KEY: &str = r"SOFTWARE\GM\J2534Wrapper";
/// The registry value under [`WRAPPER_KEY`] that names the wrapper file.
pub const WRAPPER_VALUE: &str = "FunctionLibrary";
/// The four exports `Init` resolves on the wrapper file.
pub const EXPORTS: [&str; 4] = [
    "GetDefaultDeviceInfo",
    "ClearDefaultDeviceInfo",
    "GetConnectedDeviceInfo",
    "GetDeviceStatus",
];

/// One connect string `J2534Tool.init` can hand to `SPSTool.initialize`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct InitString {
    /// Which form the connect string is: `default`, `wrapper`, `auto`, `legacy` or `connection`.
    pub form: String,
    /// The wrapper version, set only for the `wrapper` form.
    pub version: String,
    /// The tool or connection name, where the form carries one.
    pub name: String,
}

impl InitString {
    /// A form with no version and no name.
    fn form(form: &str) -> Self {
        Self {
            form: form.to_owned(),
            version: String::new(),
            name: String::new(),
        }
    }

    /// A form with a name but no version.
    fn named(form: &str, name: &str) -> Self {
        Self {
            form: form.to_owned(),
            version: String::new(),
            name: name.to_owned(),
        }
    }

    /// The `wrapper` form, with a version and a tool name.
    fn wrapper(version: &str, name: &str) -> Self {
        Self {
            form: "wrapper".to_owned(),
            version: version.to_owned(),
            name: name.to_owned(),
        }
    }
}

/// Classify the connect string.
///
/// An empty string is the default-device path. `%04.04%J2534,<name>` is the form Java builds when
/// no VCI name is set. `AUTO` and `COM<port>,<baud>` are the two forms the native `Init`
/// special-cases. Any other text is a connection name Techline already selected.
///
/// # Errors
/// Returns [`Error::Wrapper`] when the string is the `%<version>%J2534,<name>` form but the version
/// or the name is empty.
pub fn parse_init(text: &str) -> Result<InitString> {
    if text.is_empty() {
        return Ok(InitString::form("default"));
    }
    if let Some(parsed) = parse_wrapper(text)? {
        return Ok(parsed);
    }
    if let Some(parsed) = parse_auto(text) {
        return Ok(parsed);
    }
    if is_legacy(text) {
        return Ok(InitString::named("legacy", text));
    }
    Ok(InitString::named("connection", text))
}

/// Match `^%([^%]*)%J2534,(.*)$`. `Ok(None)` when the text is not this form; `Err` when the form
/// matches but the version or the name is empty.
fn parse_wrapper(text: &str) -> Result<Option<InitString>> {
    let Some(body) = text.strip_prefix('%') else {
        return Ok(None);
    };
    let Some(pct) = body.find('%') else {
        return Ok(None);
    };
    let version = &body[..pct];
    let after = &body[pct + 1..];
    let Some(name) = after.strip_prefix("J2534,") else {
        return Ok(None);
    };
    if version.is_empty() || name.is_empty() {
        return Err(Error::wrapper(
            "the wrapper form names a version and a tool",
        ));
    }
    Ok(Some(InitString::wrapper(version, name)))
}

/// Match `^AUTO(?:,(\d+))?$`.
fn parse_auto(text: &str) -> Option<InitString> {
    if text == "AUTO" {
        return Some(InitString::named("auto", ""));
    }
    let digits = text.strip_prefix("AUTO,")?;
    if !digits.is_empty() && digits.bytes().all(|b| b.is_ascii_digit()) {
        return Some(InitString::named("auto", digits));
    }
    None
}

/// Match `^COM(\d+),(\d+)$`.
fn is_legacy(text: &str) -> bool {
    let Some(rest) = text.strip_prefix("COM") else {
        return false;
    };
    let Some((port, baud)) = rest.split_once(',') else {
        return false;
    };
    !port.is_empty()
        && port.bytes().all(|b| b.is_ascii_digit())
        && !baud.is_empty()
        && baud.bytes().all(|b| b.is_ascii_digit())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_percent_form_names_the_version_and_the_tool() {
        assert_eq!(
            parse_init("%04.04%J2534,VXDIAG").unwrap(),
            InitString::wrapper("04.04", "VXDIAG")
        );
        assert_eq!(WRAPPER_KEY, r"SOFTWARE\GM\J2534Wrapper");
        assert_eq!(
            EXPORTS,
            [
                "GetDefaultDeviceInfo",
                "ClearDefaultDeviceInfo",
                "GetConnectedDeviceInfo",
                "GetDeviceStatus",
            ]
        );
    }

    #[test]
    fn an_empty_string_asks_for_the_default_device() {
        assert_eq!(parse_init("").unwrap(), InitString::form("default"));
    }

    #[test]
    fn a_selected_connection_name_is_kept() {
        assert_eq!(
            parse_init("Bosch - MDI").unwrap(),
            InitString::named("connection", "Bosch - MDI")
        );
    }

    #[test]
    fn auto_and_the_old_com_form_are_not_the_wrapper_form() {
        assert_eq!(parse_init("AUTO").unwrap(), InitString::named("auto", ""));
        assert_eq!(
            parse_init("AUTO,38400").unwrap(),
            InitString::named("auto", "38400")
        );
        assert_eq!(
            parse_init("COM4,115200").unwrap(),
            InitString::named("legacy", "COM4,115200")
        );
    }

    #[test]
    fn a_wrapper_form_without_a_name_is_refused() {
        let err = parse_init("%04.04%J2534,").unwrap_err();
        assert!(matches!(err, Error::Wrapper(_)));
        assert!(err.to_string().contains("version and a tool"));
    }
}
