---
source: "Core Rulebook"
last_update_date: 2025-03-12
document_type: core-rules
section: actions
---

# Actions Overview

Actions have effects (▶) and conditions (◆). ◆ are conditions that must be fulfilled for the operative to perform that action, whilst ▶ are effects when an operative is performing that action, including any requirements when doing so. There are four different types of actions: universal, unique, mission and free.

**Universal actions** are the most common actions you will use and can be performed by all operatives unless specified otherwise.

**Unique actions** are rarer actions in your kill team's rules. Only specified operatives can perform them.

**Mission actions** are specific to the mission or killzone you are playing. If there are any, they will be in your mission pack, killzone rules or the equipment you've selected.

Free actions can only be performed when another rule specifies, and the following rules apply:
* The conditions of the action must be met.
* It does not cost the operative any additional AP to perform the action.
* The operative would still count as performing the action for all other rules purposes. For example, if it performed the action during its activation, it wouldn't be able to perform it again during that activation.

> **Designer's Note:** If an operative performs a free action outside of their activation, it does not prevent them from performing that action during their activation, or vice versa.

> **Designer's Note:** Moving in increments allows for greater precision and clarity.

> **Designer's Note:** These movements are done in straight-line increments, rather than curves around the corner.

# Universal Actions

## REPOSITION (1AP)

▶ Move the active operative up to its Move stat to a location it can be placed. This must be done in one or more straight-line increments, and increments are always rounded up to the nearest inch.

▶ It cannot move within control range of an enemy operative, unless one or more other friendly operatives are already within control range of that enemy operative, in which case it can move within control range of that enemy operative but cannot finish the move there.

◆ An operative cannot perform this action while within control range of an enemy operative, or during the same activation in which it performed the **Fall Back** or **Charge** action.

[Derived from illustration]
**Movement Rules:**
* Movement is measured in straight-line increments
* When moving around corners, each segment must be a straight line
* Total movement cannot exceed the operative's Move stat
* Increments are always rounded up (e.g., a **2.75"** increment counts as **3"**)
* The operative must be able to be placed at the final location

## DASH (1AP)

▶ The same as the **Reposition** action, except don't use the active operative's Move stat – it can move up to **3"** instead. In addition, it cannot climb during this move, but it can drop and jump.

◆ An operative cannot perform this action while within control range of an enemy operative, or during the same activation in which it performed the **Charge** action.

> **Designer's Note:** As operatives cannot perform the same action more than once in their activation, **Dash** actions are how operatives move even further.

## FALL BACK (2AP)

▶ The same as the **Reposition** action, except the active operative can move within control range of an enemy operative, but cannot finish the move there.

◆ An operative cannot perform this action unless an enemy operative is within its control range. It cannot perform this action during the same activation in which it performed the **Reposition** or Charge action.

> **Designer's Note:** If an operative is activated within control range of an enemy operative, the **Fall Back** action is a way to withdraw. It costs 2AP, so most operatives could do no other actions in that activation.

> **Designer's Note:** The **Charge** action allows operatives to effectively close down enemies, but as they must have an Engage order to do so, they can be vulnerable to enemy shooting later on.

## CHARGE (1AP)

▶ The same as the **Reposition** action, except the active operative can move an additional **2"**.

▶ It can move, and must finish the move, within control range of an enemy operative. If it moves within control range of an enemy operative that no other friendly operatives are within control range of, it cannot leave that operative's control range.

◆ An operative cannot perform this action while it has a Conceal order, if it's already within control range of an enemy operative, or during the same activation in which it performed the **Reposition**, **Dash** or **Fall Back** action.

## PICK UP MARKER (1AP)

▶ Remove a marker the active operative controls that the **Pick Up Marker** action can be performed upon. That operative is now carrying, contesting and controlling that marker.

◆ An operative cannot perform this action while within control range of an enemy operative, or while it's already carrying a marker.

> **Designer's Note:** If there are any such markers that the **Pick Up Marker** action can be performed upon, it will be specified elsewhere, e.g. your mission pack.

## PLACE MARKER (1AP)

▶ Place a marker the active operative is carrying within its control range.

▶ If an operative carrying a marker is incapacitated, it must perform this action before being removed from the killzone, but does so for 0AP. This takes precedence over all rules that prevent it from doing so.

◆ An operative cannot perform this action during the same activation in which it already performed the **Pick Up Marker action** (unless incapacitated).

> **Designer's Note:** As above, if there are any markers the operative is carrying, it will be specified elsewhere.

## SHOOT (1AP)

▶ Shoot with the active operative by following the sequence below. The active operative's player is the attacker. The selected enemy operative's player is the defender.

◆ An operative cannot perform this action while it has a Conceal order, or while within control range of an enemy operative.

> **Designer's Note:** Unsurprisingly, Kill Team can be a very deadly game, so if you are frequently losing operatives to enemy shooting, consider playing more defensively with operatives in cover on a Conceal order.

> **Designer's Note:** In some rare instances you will be the attacker and defender, such as when shooting a friendly operative as a result of the Blast weapon rule. When this happens, you roll attack and defence dice (not your opponent).

> **Designer's Note:** Obscuring means it's less efficient to target an enemy operative through large intervening obstructions. However, this is ignored when operatives are at such obstructions – imagine them leaning around corners or through windows.

### 1. Select Weapon
The attacker selects one ranged weapon to use that their operative has and collects their attack dice – a number of D6 equal to the weapon's Atk stat.

### 2. Select Valid Target
The attacker selects an enemy operative that's a valid target and has no friendly operatives within its control range.

* If the intended target has an Engage order, it's a valid target if it's visible to the active operative.

* If the intended target has a Conceal order, it's a valid target if it's visible to the active operative and not in cover.

An operative is visible if the active operative can see it. An operative is in cover if there's intervening terrain within its control range. However, it cannot be in cover while within **2"** of the active operative.

An operative cannot be in cover from and obscured by the same terrain feature. If it would be, the defender must select one of them (cover or obscured) for that sequence when their operative is selected as the valid target.

### 3. Roll Attack Dice
The attacker rolls their attack dice. Each result that equals or beats the weapon's Hit stat is a success and is retained. Each result that doesn't is a fail and is discarded. Each result of 6 is always a critical success. Each other success is a normal success. Each result of 1 is always a fail.

If the target operative is obscured:
* The attacker must discard one success of their choice instead of retaining it.
* All the attacker's critical successes are retained as normal successes and cannot be changed to critical successes (this takes precedence over all other rules).

An operative is obscured if there's intervening Heavy terrain. However, it cannot be obscured by intervening Heavy terrain that's within **1"** of either operative.

### 4. Roll Defence Dice
The defender collects three defence dice. If the target operative is in cover, they can retain one normal success without rolling it – this is known as a cover save. They roll the remainder.

Each result that equals or beats the target's Save stat is a success and is retained. Each result that doesn't is a fail and is discarded. Each result of 6 is always a critical success. Each other success is a normal success. Each result of 1 is always a fail.

> **Designer's Note:** Remember, cover in this step usually applies to operatives with an Engage order, as a Conceal order would have prevented it from being a valid target in the first place.

### 5. Resolve Defence Dice
The defender allocates all their successful defence dice to block successful attack dice.

* A normal success can block a normal success.
* Two normal successes can block a critical success.
* A critical success can block a normal success or a critical success.

### 6. Resolve Attack Dice
All successful unblocked attack dice inflict damage on the target operative.

* A normal success inflicts damage equal to the weapon's Normal Dmg stat.
* A critical success inflicts damage equal to the weapon's Critical Dmg stat.

Any operatives that were incapacitated are removed after the active operative has finished the action.

> **Designer's Note:** Some weapons shoot multiple times in one action, such as those with the Blast and Torrent weapon rules (see `weapon rules`). Therefore, operatives aren't removed until the whole action has been resolved.

## FIGHT (1AP)

▶ Fight with the active operative by following the sequence below. The active operative's player is the attacker. The selected enemy operative's player is the defender.

◆ An operative cannot perform this action unless an enemy operative is within its control range.

> **Designer's Note:** Unlike shooting, fighting is a brutal back-and-forth duel. Be mindful of who you select to fight against, as they retaliate.

> **Designer's Note:** The difference between when an operative is fighting and when it's retaliating is important. The operative fighting is the active operative, whilst the operative retaliating is the selected enemy operative.

> **Designer's Note:** If a rule says an operative cannot retaliate, then they can still be fought against, but attack dice cannot be collected or resolved for them.

### 1. Select Enemy Operative
The attacker selects an enemy operative within the active operative's control range to fight against. That enemy operative will retaliate in this action.

### 2. Select Weapons
Both players select one melee weapon to use that their operative has and collect their attack dice – a number of D6 equal to the weapon's Atk stat.

### 3. Roll Attack Dice
Both players roll their attack dice simultaneously. Each result that equals or beats their selected weapon's Hit stat is a success and is retained. Each result that doesn't is a fail and is discarded. Each result of 6 is always a critical success. Each other success is a normal success. Each result of 1 is always a fail.

While a friendly operative is assisted by other friendly operatives, improve the Hit stat of its melee weapons by 1 for each doing so. For a friendly operative to assist them, it must be within control range of the enemy operative in that fight and not within control range of another enemy operative.

> **Designer's Note:** Having multiple friendly operatives within control range of an enemy operative doesn't allow them all to fight simultaneously, but having assists makes successful attack dice more likely.

### 4. Resolve Attack Dice
Starting with the attacker, the players alternate resolving one of their successful unblocked attack dice. The players repeat this process until one player has resolved all their dice (in which case their opponent resolves all their remaining dice), or one operative in that fight is incapacitated (see damage in `rules-3-key-principles.md`). When a player resolves a dice, they must strike or block with it.

If they strike, inflict damage on the enemy operative, then discard that dice.
* A normal success inflicts damage equal to the weapon's Normal Dmg stat.
* A critical success inflicts damage equal to the weapon's Critical Dmg stat.

If they block, they can allocate that dice to block one of their opponent's unresolved successes.
* A normal success can block a normal success.
* A critical success can block a normal success or a critical success.

> **Designer's Note:** Striking inflicts damage straight away, so it can be an effective way of damaging enemies.

> **Designer's Note:** Blocking doesn't stop a strike as it's happening, it stops a success that's yet to be resolved.

> **Designer's Note:** You can still block even if your opponent has no unresolved successes remaining. This is useful if you don't want to incapacitate the enemy operative yet.

[Summary]
The Fight action creates a back-and-forth melee combat where both operatives attack simultaneously, but resolve their successes alternately starting with the attacker. The key strategic choice is whether to strike (inflict damage immediately) or block (prevent opponent's future strikes).

## **Actions** - Key Numerical Rules Summary

| Rule/Constraint | Value |
|---|---|
| Dash movement distance | 3" |
| Charge additional movement | 2" |
| Fall Back AP cost | 2AP |
| All other Universal Actions AP cost | 1AP |
| Distance for operative to be in cover | Within 1" |
| Distance for Heavy terrain to obscure | Outside 1" |
| Defence dice (standard) | 3 |
| Critical success roll | 6 |
| Automatic fail roll | 1 |
| Cover save (automatic normal success) | 1 |