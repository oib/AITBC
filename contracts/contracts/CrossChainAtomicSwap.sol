// SPDX-License-Identifier: MIT
pragma solidity ^0.8.19;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title CrossChainAtomicSwap
 * @dev Hashed Time-Locked Contract (HTLC) for trustless cross-chain swaps.
 */
contract CrossChainAtomicSwap is ReentrancyGuard, Ownable {
    using SafeERC20 for IERC20;

    enum SwapStatus {
        INVALID,
        OPEN,
        COMPLETED,
        REFUNDED
    }

    struct Swap {
        address initiator;
        address participant;
        address token; // address(0) for native currency
        uint256 amount;
        bytes32 hashlock;
        uint256 timelock;
        SwapStatus status;
    }

    mapping(bytes32 => Swap) public swaps; // swapId => Swap mapping

    event SwapInitiated(
        bytes32 indexed swapId,
        address indexed initiator,
        address indexed participant,
        address token,
        uint256 amount,
        bytes32 hashlock,
        uint256 timelock
    );

    event SwapCompleted(
        bytes32 indexed swapId,
        address indexed participant,
        bytes32 secret
    );

    event SwapRefunded(
        bytes32 indexed swapId,
        address indexed initiator
    );

    /**
     * @dev Initiate an atomic swap. The amount is locked in this contract.
     */
    function initiateSwap(
        bytes32 _swapId,
        address _participant,
        address _token,
        uint256 _amount,
        bytes32 _hashlock,
        uint256 _timelock
    ) external payable nonReentrant {
        require(swaps[_swapId].status == SwapStatus.INVALID, "Swap ID already exists");
        require(_participant != address(0), "Invalid participant");
        require(_timelock > block.timestamp, "Timelock must be in the future");
        require(_amount > 0, "Amount must be > 0");

        if (_token == address(0)) {
            require(msg.value == _amount, "Incorrect ETH amount sent");
        } else {
            require(msg.value == 0, "ETH sent but ERC20 token specified");
            IERC20(_token).safeTransferFrom(msg.sender, address(this), _amount);
        }

        swaps[_swapId] = Swap({
            initiator: msg.sender,
            participant: _participant,
            token: _token,
            amount: _amount,
            hashlock: _hashlock,
            timelock: _timelock,
            status: SwapStatus.OPEN
        });

        emit SwapInitiated(
            _swapId,
            msg.sender,
            _participant,
            _token,
            _amount,
            _hashlock,
            _timelock
        );
    }

    /**
     * @dev Complete the swap by providing the secret that hashes to the hashlock.
     */
    function completeSwap(bytes32 _swapId, bytes32 _secret) external nonReentrant {
        Swap storage swap = swaps[_swapId];

        require(swap.status == SwapStatus.OPEN, "Swap is not open");
        require(block.timestamp < swap.timelock, "Swap timelock expired");
        require(
            sha256(abi.encodePacked(_secret)) == swap.hashlock,
            "Invalid secret"
        );

        swap.status = SwapStatus.COMPLETED;

        if (swap.token == address(0)) {
            (bool success, ) = payable(swap.participant).call{value: swap.amount}("");
            require(success, "ETH transfer failed");
        } else {
            IERC20(swap.token).safeTransfer(swap.participant, swap.amount);
        }

        emit SwapCompleted(_swapId, swap.participant, _secret);
    }

    /**
     * @dev Refund the swap if the timelock has expired and it wasn't completed.
     */
    function refundSwap(bytes32 _swapId) external nonReentrant {
        Swap storage swap = swaps[_swapId];

        require(swap.status == SwapStatus.OPEN, "Swap is not open");
        require(block.timestamp >= swap.timelock, "Swap timelock not yet expired");

        swap.status = SwapStatus.REFUNDED;

        if (swap.token == address(0)) {
            (bool success, ) = payable(swap.initiator).call{value: swap.amount}("");
            require(success, "ETH transfer failed");
        } else {
            IERC20(swap.token).safeTransfer(swap.initiator, swap.amount);
        }

        emit SwapRefunded(_swapId, swap.initiator);
    }
}
