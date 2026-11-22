//! The crate error type.
//!
//! The Python original raised four `ValueError` subclasses: `Vit1Error` (a module read cannot be
//! attached), `WrapperError` (a connect string is not a known form), `HandoffError` (a captured
//! read cannot be mapped onto a rule), and `SpsInfoError` (a VIN is malformed, from the sibling
//! `techlinekit`). The Rust port keeps those four categories as one [`Error`] enum so handoff
//! functions can return either a handoff or a VIT1 message, the way the Python ones propagate both.
//! A fifth category, `Proxy`, has no Python original: it records a malformed GM J2534 proxy
//! allow/deny list, a device-bound call on a device that is not open, or a version or library path
//! that does not fit its buffer — the contract [`crate::proxy`] exposes without loading a DLL.
//! Each variant carries only a human-readable message, which is what its `Display` prints.

use core::fmt;

/// An invalid value or a read that cannot be shaped into a request.
///
/// The variant records which Python `ValueError` subclass this stands in for; the message is the
/// same text the original raised.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Error {
    /// A module read cannot be attached to the programming-data request (`Vit1Error`).
    Vit1(String),
    /// The init string is not one of the forms `Init` logs (`WrapperError`).
    Wrapper(String),
    /// The captured read cannot be mapped onto a saved-read rule (`HandoffError`).
    Handoff(String),
    /// A VIN is not 17 characters or uses `I`, `O` or `Q` (`SpsInfoError`).
    SpsInfo(String),
    /// A GM J2534 proxy contract violation: a malformed allow/deny list, a device-bound call on a
    /// device that is not open, or a string that does not fit its 256-byte buffer. Rust-only; the
    /// Python package had no J2534 proxy.
    Proxy(String),
}

impl Error {
    /// A `Vit1Error`: a module read cannot be attached to the request.
    pub(crate) fn vit1(message: impl Into<String>) -> Self {
        Error::Vit1(message.into())
    }

    /// A `WrapperError`: the connect string is not a known form.
    pub(crate) fn wrapper(message: impl Into<String>) -> Self {
        Error::Wrapper(message.into())
    }

    /// A `HandoffError`: the captured read cannot be mapped onto a rule.
    pub(crate) fn handoff(message: impl Into<String>) -> Self {
        Error::Handoff(message.into())
    }

    /// An `SpsInfoError`: the VIN is malformed.
    pub(crate) fn spsinfo(message: impl Into<String>) -> Self {
        Error::SpsInfo(message.into())
    }

    /// A `Proxy` error: the GM J2534 proxy contract was given a bad list, an unknown device, or an
    /// oversize string.
    pub(crate) fn proxy(message: impl Into<String>) -> Self {
        Error::Proxy(message.into())
    }

    /// The error message, without the category.
    #[must_use]
    pub fn message(&self) -> &str {
        match self {
            Error::Vit1(m)
            | Error::Wrapper(m)
            | Error::Handoff(m)
            | Error::SpsInfo(m)
            | Error::Proxy(m) => m,
        }
    }
}

impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.message())
    }
}

impl std::error::Error for Error {}

/// A `Result` whose error is this crate's [`Error`].
pub type Result<T> = core::result::Result<T, Error>;
