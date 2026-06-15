// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract AIToken is ERC20, Ownable {
    uint256 public constant MAX_SUPPLY = 1_000_000_000 * 10**18; // 1 billion tokens
    uint256 public constant MINTING_COOLDOWN = 1 days; // 1 day cooldown between mints
    uint256 public lastMintTime;

    constructor(uint256 initialSupply) ERC20("AI Token", "AIT")  {
        require(initialSupply <= MAX_SUPPLY, "Initial supply exceeds max supply");
        _mint(msg.sender, initialSupply);
    }

    function mint(address to, uint256 amount) public onlyOwner {
        require(totalSupply() + amount <= MAX_SUPPLY, "Minting would exceed max supply");
        require(block.timestamp >= lastMintTime + MINTING_COOLDOWN, "Minting cooldown not elapsed");

        _mint(to, amount);
        lastMintTime = block.timestamp;
    }
}
