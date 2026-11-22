//! `spskit`: the GM SPS2 programming request, in Rust.
//!
//! The crate builds the GM SPS2 "VIT1" `getProgrammingData` request body from a saved module read,
//! a VIN and a controller code, and classifies the GM J2534 wrapper connect string. It is a
//! library: it attaches a saved read as the VIT1 control-module block and returns the request body
//! or the next screen. It does **not** program a vehicle, post to TDS, download a calibration, open
//! a port, derive a security key, or speak SAE J2534.
//!
//! The TDS and Techline Connect client (sign-in, licensed downloads, SPS Info) is the separate
//! `techlinekit`; the one rule it provides to this crate, VIN validation, is reproduced in [`vin`]
//! because there is no Rust `techlinekit`. The J2534 dongle is `vcxtoolkit`. The UDS/GMLAN service
//! framing the format decoders key on is read from the sibling `udskit` crate, so there is one Rust
//! source of truth for it.
//!
//! The decompiled `spsvcs`/`J2534Tool` paths the shapes follow are recorded in `docs/sources.md`.
//! This is behaviour-for-behaviour the Python package it replaces.

pub mod error;
pub mod handoff;
pub mod vin;
pub mod vit1;
pub mod wrapper;

pub use error::{Error, Result};
