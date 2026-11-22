//! VIN validation, the one piece `spskit` needs from the TDS client.
//!
//! The Python package imports `techlinekit.spsinfo.check_vin` and `SpsInfoError` and nothing else.
//! There is no Rust `techlinekit`, so the single rule those provide is reproduced here: a VIN is
//! 17 characters from `A`-`Z` and `0`-`9` with `I`, `O` and `Q` excluded (the digits a VIN never
//! uses). Nothing else from the TDS client crosses into this crate.

use crate::error::{Error, Result};

/// Validate a VIN and return it unchanged.
///
/// A VIN is 17 characters drawn from `A`-`H`, `J`-`N`, `P`, `R`-`Z` and `0`-`9`; the letters `I`,
/// `O` and `Q` are not used, since they read as `1`, `0` and `0`.
///
/// # Errors
/// Returns [`Error::SpsInfo`] when the string is not exactly 17 of those characters.
pub fn check_vin(vin: &str) -> Result<&str> {
    if vin.len() == 17 && vin.chars().all(is_vin_char) {
        Ok(vin)
    } else {
        Err(Error::spsinfo(
            "a VIN is 17 characters and does not use I, O or Q",
        ))
    }
}

/// Whether `c` is a character a VIN may contain: `A`-`Z` without `I`/`O`/`Q`, or `0`-`9`.
fn is_vin_char(c: char) -> bool {
    matches!(c, 'A'..='H' | 'J'..='N' | 'P' | 'R'..='Z' | '0'..='9')
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_17_character_vin_without_ioq_is_returned() {
        assert_eq!(check_vin("1G1TE5TVN00000001").unwrap(), "1G1TE5TVN00000001");
    }

    #[test]
    fn a_short_or_illegal_vin_is_refused() {
        assert!(check_vin("TOOSHORT").is_err());
        assert!(check_vin("1G1TE5TVN0000000").is_err()); // 16 chars
        assert!(check_vin("1G1TE5TVN000000011").is_err()); // 18 chars
        assert!(check_vin("IG1TE5TVN00000001").is_err()); // leading I
        assert!(check_vin("OG1TE5TVN00000001").is_err()); // leading O
        assert!(check_vin("QG1TE5TVN00000001").is_err()); // leading Q
        assert!(check_vin("1g1te5tvn00000001").is_err()); // lowercase
    }
}
