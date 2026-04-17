// Copyright (c) 2026 BearTec. Licensed under BUSL-1.1 until 2030-04-09; then MIT.
// SPDX-License-Identifier: BUSL-1.1
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

/**
 * @dev Minimal ERC-20 mock for unit tests.
 *      Exposes a public mint() function — not for production use.
 */
contract ERC20Mock is ERC20 {
    uint8 private _dec;

    constructor(string memory name, string memory symbol, uint8 dec_)
        ERC20(name, symbol)
    {
        _dec = dec_;
    }

    function decimals() public view override returns (uint8) { return _dec; }

    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
